import jwt from 'jsonwebtoken';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();
const JWT_SECRET = process.env.JWT_SECRET || 'your-super-secret-jwt-key-change-in-production';
const JWT_EXPIRES_IN = '7d';
const JWT_REFRESH_EXPIRES_IN = '30d';

export function generateAccessToken(user) {
  return jwt.sign(
    { 
      id: user.id, 
      email: user.email, 
      organizationId: user.organizationId,
      role: user.role 
    },
    JWT_SECRET,
    { expiresIn: JWT_EXPIRES_IN }
  );
}

export function generateRefreshToken(user) {
  return jwt.sign(
    { id: user.id, type: 'refresh' },
    JWT_SECRET,
    { expiresIn: JWT_REFRESH_EXPIRES_IN }
  );
}

export function verifyToken(token) {
  try {
    return jwt.verify(token, JWT_SECRET);
  } catch (error) {
    return null;
  }
}

export async function authenticate(req, res, next) {
  try {
    const authHeader = req.headers.authorization;
    
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return res.status(401).json({ error: 'No token provided' });
    }

    const token = authHeader.substring(7);
    const decoded = verifyToken(token);

    if (!decoded) {
      return res.status(401).json({ error: 'Invalid or expired token' });
    }

    // Verify user still exists and is active
    const user = await prisma.user.findUnique({
      where: { id: decoded.id },
      include: {
        organization: true,
      },
    });

    if (!user) {
      return res.status(401).json({ error: 'User not found' });
    }

    if (user.organization && user.organization.status !== 'active') {
      return res.status(403).json({ error: 'Organization is not active' });
    }

    req.user = {
      id: user.id,
      email: user.email,
      name: user.name,
      organizationId: user.organizationId,
      role: user.role,
      organization: user.organization,
    };

    next();
  } catch (error) {
    console.error('Auth error:', error);
    res.status(500).json({ error: 'Authentication failed' });
  }
}

export async function authenticateApiKey(req, res, next) {
  try {
    const apiKey = req.headers['x-api-key'] || req.query.api_key;

    if (!apiKey) {
      return res.status(401).json({ error: 'API key required' });
    }

    const keyRecord = await prisma.apiKey.findUnique({
      where: { key: apiKey },
      include: {
        organization: true,
        createdBy: true,
      },
    });

    if (!keyRecord) {
      return res.status(401).json({ error: 'Invalid API key' });
    }

    if (keyRecord.expiresAt && new Date(keyRecord.expiresAt) < new Date()) {
      return res.status(401).json({ error: 'API key expired' });
    }

    if (keyRecord.organization.status !== 'active') {
      return res.status(403).json({ error: 'Organization is not active' });
    }

    // Update last used
    await prisma.apiKey.update({
      where: { id: keyRecord.id },
      data: { lastUsed: new Date() },
    });

    req.user = {
      id: keyRecord.createdById,
      email: keyRecord.createdBy.email,
      organizationId: keyRecord.organizationId,
      role: 'API_KEY',
      apiKey: keyRecord,
      permissions: keyRecord.permissions,
      organization: keyRecord.organization,
    };

    req.apiKey = keyRecord;
    next();
  } catch (error) {
    console.error('API Key auth error:', error);
    res.status(500).json({ error: 'Authentication failed' });
  }
}

// Optional authentication - doesn't fail if no token
export async function optionalAuth(req, res, next) {
  try {
    const authHeader = req.headers.authorization;
    
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return next();
    }

    const token = authHeader.substring(7);
    const decoded = verifyToken(token);

    if (!decoded) {
      return next();
    }

    const user = await prisma.user.findUnique({
      where: { id: decoded.id },
      include: { organization: true },
    });

    if (user && user.organization?.status === 'active') {
      req.user = {
        id: user.id,
        email: user.email,
        name: user.name,
        organizationId: user.organizationId,
        role: user.role,
        organization: user.organization,
      };
    }

    next();
  } catch (error) {
    // Silently continue without auth
    next();
  }
}

export function requireOrganizationAccess() {
  return (req, res, next) => {
    if (!req.user?.organizationId) {
      return res.status(403).json({ error: 'Organization access required' });
    }
    next();
  };
}

export { JWT_SECRET, JWT_EXPIRES_IN, JWT_REFRESH_EXPIRES_IN };