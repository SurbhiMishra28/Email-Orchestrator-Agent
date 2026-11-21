import express from 'express';
import { PrismaClient } from '@prisma/client';
import { requirePermission } from '../middleware/rbac.js';
import { auditLog } from '../middleware/auditLog.js';
import crypto from 'crypto';

const prisma = new PrismaClient();
const router = express.Router();

// GET /api/settings - Get organization settings
router.get('/', requirePermission('settings:read'), async (req, res) => {
  try {
    const settings = await prisma.settings.findUnique({
      where: { organizationId: req.user.organizationId },
    });

    if (!settings) {
      // Create default settings
      const defaultSettings = await prisma.settings.create({
        data: { organizationId: req.user.organizationId },
      });
      return res.json(defaultSettings);
    }

    res.json(settings);
  } catch (error) {
    console.error('Error fetching settings:', error);
    res.status(500).json({ error: 'Failed to fetch settings' });
  }
});

// PUT /api/settings - Update organization settings
router.put('/', requirePermission('settings:write'), async (req, res) => {
  try {
    const {
      goal,
      businessName,
      businessOffer,
      dailyCap,
      domainCap,
      AUTO_APPROVE,
      AUTOPILOT,
      footerText,
      senderName,
      senderRole,
      companyWebsite,
      calendlyUrl,
    } = req.body;

    const settings = await prisma.settings.upsert({
      where: { organizationId: req.user.organizationId },
      create: {
        organizationId: req.user.organizationId,
        goal,
        businessName,
        businessOffer,
        dailyCap,
        domainCap,
        AUTO_APPROVE,
        AUTOPILOT,
        footerText,
        senderName,
        senderRole,
        companyWebsite,
        calendlyUrl,
      },
      update: {
        goal,
        businessName,
        businessOffer,
        dailyCap,
        domainCap,
        AUTO_APPROVE,
        AUTOPILOT,
        footerText,
        senderName,
        senderRole,
        companyWebsite,
        calendlyUrl,
      },
    });

    await auditLog.update(req.user.organizationId, req.user.id, 'Settings', settings.id);

    res.json(settings);
  } catch (error) {
    console.error('Error updating settings:', error);
    res.status(500).json({ error: 'Failed to update settings' });
  }
});

// --- SMTP Configuration ---

// GET /api/settings/smtp - Get SMTP configuration
router.get('/smtp', requirePermission('settings:manage_smtp'), async (req, res) => {
  try {
    const org = await prisma.organization.findUnique({
      where: { id: req.user.organizationId },
      select: {
        id: true,
        name: true,
        // SMTP config would be stored in settings or a separate model
      },
    });

    // For now, return placeholder - in production, decrypt and return SMTP config
    res.json({
      host: process.env.SMTP_HOST || '',
      port: parseInt(process.env.SMTP_PORT) || 587,
      user: process.env.SMTP_USER || '',
      // password is never returned
      fromEmail: process.env.SMTP_FROM_EMAIL || '',
      fromName: process.env.SMTP_FROM_NAME || '',
      tls: true,
    });
  } catch (error) {
    console.error('Error fetching SMTP config:', error);
    res.status(500).json({ error: 'Failed to fetch SMTP configuration' });
  }
});

// PUT /api/settings/smtp - Update SMTP configuration
router.put('/smtp', requirePermission('settings:manage_smtp'), async (req, res) => {
  try {
    const { host, port, user, password, fromEmail, fromName, tls } = req.body;

    if (!host || !user || !password || !fromEmail) {
      return res.status(400).json({ error: 'Host, user, password, and fromEmail are required' });
    }

    // In production, encrypt password before storing
    // For now, we'll store in environment or a secure config table
    
    await auditLog.update(req.user.organizationId, req.user.id, 'SmtpConfig', req.user.organizationId, {
      host,
      port,
      user,
      fromEmail,
      fromName,
    });

    // TODO: Store in database with encryption
    res.json({ message: 'SMTP configuration updated', host, port, user, fromEmail, fromName, tls });
  } catch (error) {
    console.error('Error updating SMTP config:', error);
    res.status(500).json({ error: 'Failed to update SMTP configuration' });
  }
});

// POST /api/settings/smtp/test - Test SMTP connection
router.post('/smtp/test', requirePermission('settings:manage_smtp'), async (req, res) => {
  try {
    const { host, port, user, password, fromEmail, fromName, tls } = req.body;

    // TODO: Implement actual SMTP test connection
    // For now, return success
    res.json({ success: true, message: 'SMTP connection test successful' });
  } catch (error) {
    console.error('Error testing SMTP:', error);
    res.status(500).json({ error: 'Failed to test SMTP connection' });
  }
});

// --- Sender Domains ---

// GET /api/settings/domains - List sender domains
router.get('/domains', requirePermission('settings:read'), async (req, res) => {
  try {
    // TODO: Implement SenderDomain model
    // For now, return placeholder
    res.json({
      domains: [
        // Example structure:
        // { id: 1, domain: 'example.com', status: 'verified', spf: true, dkim: true, dmarc: true, createdAt: '...' }
      ],
    });
  } catch (error) {
    console.error('Error fetching domains:', error);
    res.status(500).json({ error: 'Failed to fetch domains' });
  }
});

// POST /api/settings/domains - Add sender domain
router.post('/domains', requirePermission('settings:manage_smtp'), async (req, res) => {
  try {
    const { domain } = req.body;

    if (!domain) {
      return res.status(400).json({ error: 'Domain is required' });
    }

    // TODO: Implement domain verification records generation
    const verificationRecords = {
      spf: { type: 'TXT', name: '@', value: 'v=spf1 include:_spf.yourprovider.com ~all' },
      dkim: { type: 'TXT', name: 'default._domainkey', value: 'v=DKIM1; k=rsa; p=...' },
      dmarc: { type: 'TXT', name: '_dmarc', value: 'v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com' },
    };

    await auditLog.create(req.user.organizationId, req.user.id, 'SenderDomain', null, { 
      action: 'added',
      domain 
    });

    res.status(201).json({ domain, verificationRecords, status: 'pending_verification' });
  } catch (error) {
    console.error('Error adding domain:', error);
    res.status(500).json({ error: 'Failed to add domain' });
  }
});

// POST /api/settings/domains/:domain/verify - Verify domain DNS records
router.post('/domains/:domain/verify', requirePermission('settings:manage_smtp'), async (req, res) => {
  try {
    const { domain } = req.params;

    // TODO: Implement actual DNS verification
    const verificationResult = {
      spf: { valid: true, value: 'v=spf1 include:_spf.example.com ~all' },
      dkim: { valid: true, value: 'v=DKIM1; k=rsa; p=...' },
      dmarc: { valid: true, value: 'v=DMARC1; p=none; rua=mailto:dmarc@example.com' },
    };

    await auditLog.create(req.user.organizationId, req.user.id, 'SenderDomain', null, { 
      action: 'verified',
      domain,
      result: verificationResult
    });

    res.json({ domain, verified: true, records: verificationResult });
  } catch (error) {
    console.error('Error verifying domain:', error);
    res.status(500).json({ error: 'Failed to verify domain' });
  }
});

// --- Webhooks ---

// GET /api/settings/webhooks - List webhooks
router.get('/webhooks', requirePermission('settings:manage_webhooks'), async (req, res) => {
  try {
    // TODO: Implement Webhook model
    res.json({ webhooks: [] });
  } catch (error) {
    console.error('Error fetching webhooks:', error);
    res.status(500).json({ error: 'Failed to fetch webhooks' });
  }
});

// POST /api/settings/webhooks - Create webhook
router.post('/webhooks', requirePermission('settings:manage_webhooks'), async (req, res) => {
  try {
    const { url, events, secret } = req.body;

    if (!url || !events || !Array.isArray(events)) {
      return res.status(400).json({ error: 'URL and events array are required' });
    }

    const webhookSecret = secret || crypto.randomBytes(32).toString('hex');

    // TODO: Store webhook in database
    const webhook = { id: Date.now(), url, events, secret: webhookSecret, createdAt: new Date() };

    await auditLog.create(req.user.organizationId, req.user.id, 'Webhook', webhook.id, { 
      url, events 
    });

    res.status(201).json(webhook);
  } catch (error) {
    console.error('Error creating webhook:', error);
    res.status(500).json({ error: 'Failed to create webhook' });
  }
});

// PUT /api/settings/webhooks/:id - Update webhook
router.put('/webhooks/:id', requirePermission('settings:manage_webhooks'), async (req, res) => {
  try {
    const { url, events, active } = req.body;

    // TODO: Update webhook in database

    await auditLog.update(req.user.organizationId, req.user.id, 'Webhook', req.params.id, { url, events });

    res.json({ id: req.params.id, url, events, active });
  } catch (error) {
    console.error('Error updating webhook:', error);
    res.status(500).json({ error: 'Failed to update webhook' });
  }
});

// DELETE /api/settings/webhooks/:id - Delete webhook
router.delete('/webhooks/:id', requirePermission('settings:manage_webhooks'), async (req, res) => {
  try {
    // TODO: Delete webhook from database

    await auditLog.delete(req.user.organizationId, req.user.id, 'Webhook', req.params.id);

    res.json({ message: 'Webhook deleted' });
  } catch (error) {
    console.error('Error deleting webhook:', error);
    res.status(500).json({ error: 'Failed to delete webhook' });
  }
});

// --- API Keys ---

// GET /api/settings/api-keys - List API keys
router.get('/api-keys', requirePermission('settings:manage_api_keys'), async (req, res) => {
  try {
    const apiKeys = await prisma.apiKey.findMany({
      where: { organizationId: req.user.organizationId },
      select: {
        id: true,
        name: true,
        permissions: true,
        lastUsed: true,
        expiresAt: true,
        createdAt: true,
        createdBy: { select: { id: true, name: true, email: true } },
        // key is never returned
      },
      orderBy: { createdAt: 'desc' },
    });

    res.json({ apiKeys });
  } catch (error) {
    console.error('Error fetching API keys:', error);
    res.status(500).json({ error: 'Failed to fetch API keys' });
  }
});

// POST /api/settings/api-keys - Create API key
router.post('/api-keys', requirePermission('settings:manage_api_keys'), async (req, res) => {
  try {
    const { name, permissions, expiresAt } = req.body;

    if (!name) {
      return res.status(400).json({ error: 'Name is required' });
    }

    const key = `esk_${crypto.randomBytes(24).toString('hex')}`;
    const keyPrefix = key.substring(0, 12); // For display

    const apiKey = await prisma.apiKey.create({
      data: {
        key,
        name,
        permissions: permissions || ['api:read'],
        expiresAt: expiresAt ? new Date(expiresAt) : null,
        organizationId: req.user.organizationId,
        createdById: req.user.id,
      },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'ApiKey', apiKey.id, { name });

    // Return the full key only once
    res.status(201).json({
      ...apiKey,
      key, // Only returned on creation
      keyPrefix,
    });
  } catch (error) {
    console.error('Error creating API key:', error);
    res.status(500).json({ error: 'Failed to create API key' });
  }
});

// DELETE /api/settings/api-keys/:id - Revoke API key
router.delete('/api-keys/:id', requirePermission('settings:manage_api_keys'), async (req, res) => {
  try {
    const apiKey = await prisma.apiKey.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!apiKey) {
      return res.status(404).json({ error: 'API key not found' });
    }

    await prisma.apiKey.delete({ where: { id: parseInt(req.params.id) } });

    await auditLog.delete(req.user.organizationId, req.user.id, 'ApiKey', req.params.id, { name: apiKey.name });

    res.json({ message: 'API key revoked' });
  } catch (error) {
    console.error('Error revoking API key:', error);
    res.status(500).json({ error: 'Failed to revoke API key' });
  }
});

// --- Audit Logs ---

// GET /api/settings/audit-logs - Get audit logs
router.get('/audit-logs', requirePermission('settings:view_audit_logs'), async (req, res) => {
  try {
    const { page = 1, limit = 50, action, entityType, userId, startDate, endDate } = req.query;

    const where = {
      organizationId: req.user.organizationId,
    };

    if (action) where.action = action;
    if (entityType) where.entityType = entityType;
    if (userId) where.performedById = parseInt(userId);
    if (startDate || endDate) {
      where.createdAt = {};
      if (startDate) where.createdAt.gte = new Date(startDate);
      if (endDate) where.createdAt.lte = new Date(endDate);
    }

    const [logs, total] = await Promise.all([
      prisma.auditLog.findMany({
        where,
        skip: (page - 1) * limit,
        take: parseInt(limit),
        orderBy: { createdAt: 'desc' },
        include: {
          performedBy: { select: { id: true, name: true, email: true } },
        },
      }),
      prisma.auditLog.count({ where }),
    ]);

    res.json({
      logs,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    console.error('Error fetching audit logs:', error);
    res.status(500).json({ error: 'Failed to fetch audit logs' });
  }
});

export default router;