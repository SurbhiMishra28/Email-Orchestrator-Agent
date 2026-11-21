import { Redis } from 'ioredis';

const redis = new Redis(process.env.REDIS_URL || 'redis://localhost:6379');

const RATE_LIMITS = {
  // Default limits
  default: { windowMs: 15 * 60 * 1000, max: 100 }, // 100 requests per 15 minutes
  
  // Auth endpoints - stricter
  auth: { windowMs: 15 * 60 * 1000, max: 10 }, // 10 requests per 15 minutes
  'auth:login': { windowMs: 15 * 60 * 1000, max: 5 }, // 5 login attempts per 15 minutes
  'auth:register': { windowMs: 60 * 60 * 1000, max: 3 }, // 3 registrations per hour
  
  // API endpoints
  api: { windowMs: 60 * 1000, max: 60 }, // 60 requests per minute
  'api:write': { windowMs: 60 * 1000, max: 30 }, // 30 write requests per minute
  
  // Import/Export - heavier operations
  import: { windowMs: 60 * 60 * 1000, max: 10 }, // 10 imports per hour
  export: { windowMs: 60 * 60 * 1000, max: 20 }, // 20 exports per hour
  
  // Campaign sending
  'campaigns:send': { windowMs: 60 * 60 * 1000, max: 50 }, // 50 campaign sends per hour
  
  // AI generation
  'ai:generate': { windowMs: 60 * 1000, max: 20 }, // 20 AI generations per minute
  
  // Webhook endpoints
  webhook: { windowMs: 60 * 1000, max: 200 }, // 200 webhooks per minute
};

export function rateLimit(keyPrefix, options = {}) {
  const config = RATE_LIMITS[keyPrefix] || options;
  const { windowMs = 15 * 60 * 1000, max = 100 } = config;

  return async (req, res, next) => {
    try {
      // Generate key based on IP + user ID + prefix
      const ip = req.ip || req.connection.remoteAddress || 'unknown';
      const userId = req.user?.id || 'anonymous';
      const key = `ratelimit:${keyPrefix}:${ip}:${userId}`;

      const current = await redis.incr(key);
      
      if (current === 1) {
        await redis.pexpire(key, windowMs);
      }

      const ttl = await redis.pttl(key);
      const resetTime = Date.now() + ttl;

      res.set({
        'X-RateLimit-Limit': max,
        'X-RateLimit-Remaining': Math.max(0, max - current),
        'X-RateLimit-Reset': Math.ceil(resetTime / 1000),
      });

      if (current > max) {
        return res.status(429).json({
          error: 'Too Many Requests',
          message: `Rate limit exceeded. Try again in ${Math.ceil(ttl / 1000)} seconds.`,
          retryAfter: Math.ceil(ttl / 1000),
        });
      }

      next();
    } catch (error) {
      console.error('Rate limit error:', error);
      // Fail open - don't block requests if Redis is down
      next();
    }
  };
}

// Specific rate limiters for common use cases
export const rateLimiters = {
  default: rateLimit('default'),
  auth: rateLimit('auth'),
  login: rateLimit('auth:login'),
  register: rateLimit('auth:register'),
  api: rateLimit('api'),
  apiWrite: rateLimit('api:write'),
  import: rateLimit('import'),
  export: rateLimit('export'),
  campaignSend: rateLimit('campaigns:send'),
  aiGenerate: rateLimit('ai:generate'),
  webhook: rateLimit('webhook'),
};

export async function checkRateLimit(keyPrefix, identifier, customMax, customWindowMs) {
  const key = `ratelimit:${keyPrefix}:${identifier}`;
  const windowMs = customWindowMs || 15 * 60 * 1000;
  const max = customMax || 100;

  const current = await redis.incr(key);
  if (current === 1) {
    await redis.pexpire(key, windowMs);
  }

  const ttl = await redis.pttl(key);
  
  return {
    allowed: current <= max,
    current,
    max,
    remaining: Math.max(0, max - current),
    resetTime: Date.now() + ttl,
  };
}