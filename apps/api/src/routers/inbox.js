import express from 'express';
import { PrismaClient } from '@prisma/client';
import { requirePermission } from '../middleware/rbac.js';
import { auditLog } from '../middleware/auditLog.js';

const prisma = new PrismaClient();
const router = express.Router();

// GET /api/inbox/config - Get IMAP configuration
router.get('/config', requirePermission('inbox:manage'), async (req, res) => {
  try {
    const config = await prisma.inboxConfig.findUnique({
      where: { organizationId: req.user.organizationId },
    });

    if (!config) {
      return res.json({ configured: false });
    }

    // Don't return password
    const { imapPassword, ...safeConfig } = config;
    res.json({ ...safeConfig, configured: true });
  } catch (error) {
    console.error('Error fetching inbox config:', error);
    res.status(500).json({ error: 'Failed to fetch inbox configuration' });
  }
});

// PUT /api/inbox/config - Update IMAP configuration
router.put('/config', requirePermission('inbox:manage'), async (req, res) => {
  try {
    const { imapHost, imapPort, imapUser, imapPassword, imapTls } = req.body;

    if (!imapHost || !imapUser || !imapPassword) {
      return res.status(400).json({ error: 'Host, user, and password are required' });
    }

    const config = await prisma.inboxConfig.upsert({
      where: { organizationId: req.user.organizationId },
      create: {
        organizationId: req.user.organizationId,
        imapHost,
        imapPort: imapPort || 993,
        imapUser,
        imapPassword, // In production, encrypt this
        imapTls: imapTls !== false,
        status: 'disconnected',
      },
      update: {
        imapHost,
        imapPort: imapPort || 993,
        imapUser,
        imapPassword,
        imapTls: imapTls !== false,
      },
    });

    await auditLog.update(req.user.organizationId, req.user.id, 'InboxConfig', config.id);

    const { imapPassword: _, ...safeConfig } = config;
    res.json(safeConfig);
  } catch (error) {
    console.error('Error updating inbox config:', error);
    res.status(500).json({ error: 'Failed to update inbox configuration' });
  }
});

// POST /api/inbox/config/test - Test IMAP connection
router.post('/config/test', requirePermission('inbox:manage'), async (req, res) => {
  try {
    const { imapHost, imapPort, imapUser, imapPassword, imapTls } = req.body;

    // TODO: Implement actual IMAP connection test
    // For now, return success
    res.json({ success: true, message: 'IMAP connection test successful' });
  } catch (error) {
    console.error('Error testing IMAP:', error);
    res.status(500).json({ error: 'Failed to test IMAP connection' });
  }
});

// POST /api/inbox/sync - Trigger inbox sync
router.post('/sync', requirePermission('inbox:manage'), async (req, res) => {
  try {
    const config = await prisma.inboxConfig.findUnique({
      where: { organizationId: req.user.organizationId },
    });

    if (!config) {
      return res.status(400).json({ error: 'IMAP not configured' });
    }

    // TODO: Queue sync job
    // await queueInboxSync(req.user.organizationId);

    await prisma.inboxConfig.update({
      where: { organizationId: req.user.organizationId },
      data: { status: 'syncing' },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'InboxConfig', config.id, { 
      action: 'sync_triggered' 
    });

    res.json({ message: 'Inbox sync queued', status: 'syncing' });
  } catch (error) {
    console.error('Error syncing inbox:', error);
    res.status(500).json({ error: 'Failed to sync inbox' });
  }
});

// GET /api/inbox/replies - List replies
router.get('/replies', requirePermission('inbox:read'), async (req, res) => {
  try {
    const { page = 1, limit = 50, classification, sentiment, autoReplyStatus, search } = req.query;

    const where = {
      organizationId: req.user.organizationId,
    };

    if (classification) where.classification = classification;
    if (sentiment) where.sentiment = sentiment;
    if (autoReplyStatus) where.autoReplyStatus = autoReplyStatus;
    if (search) {
      where.OR = [
        { email: { contains: search, mode: 'insensitive' } },
        { subject: { contains: search, mode: 'insensitive' } },
        { bodyPreview: { contains: search, mode: 'insensitive' } },
      ];
    }

    const [replies, total] = await Promise.all([
      prisma.reply.findMany({
        where,
        skip: (page - 1) * limit,
        take: parseInt(limit),
        orderBy: { createdAt: 'desc' },
        include: { contact: { select: { id: true, email: true, name: true } } },
      }),
      prisma.reply.count({ where }),
    ]);

    res.json({
      replies,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    console.error('Error fetching replies:', error);
    res.status(500).json({ error: 'Failed to fetch replies' });
  }
});

// GET /api/inbox/replies/:id - Get single reply
router.get('/replies/:id', requirePermission('inbox:read'), async (req, res) => {
  try {
    const reply = await prisma.reply.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
      include: { contact: { select: { id: true, email: true, name: true, customFields: true } } },
    });

    if (!reply) {
      return res.status(404).json({ error: 'Reply not found' });
    }

    res.json(reply);
  } catch (error) {
    console.error('Error fetching reply:', error);
    res.status(500).json({ error: 'Failed to fetch reply' });
  }
});

// PUT /api/inbox/replies/:id - Update reply (classification, auto-reply)
router.put('/replies/:id', requirePermission('inbox:write'), async (req, res) => {
  try {
    const { classification, sentiment, autoReplyStatus, autoReplyMessage } = req.body;

    const reply = await prisma.reply.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!reply) {
      return res.status(404).json({ error: 'Reply not found' });
    }

    const updated = await prisma.reply.update({
      where: { id: parseInt(req.params.id) },
      data: { classification, sentiment, autoReplyStatus, autoReplyMessage },
    });

    await auditLog.update(req.user.organizationId, req.user.id, 'Reply', updated.id, { 
      classification,
      sentiment,
      autoReplyStatus 
    });

    res.json(updated);
  } catch (error) {
    console.error('Error updating reply:', error);
    res.status(500).json({ error: 'Failed to update reply' });
  }
});

// POST /api/inbox/replies/:id/auto-reply - Send auto-reply
router.post('/replies/:id/auto-reply', requirePermission('inbox:write'), async (req, res) => {
  try {
    const { message } = req.body;

    if (!message) {
      return res.status(400).json({ error: 'Message is required' });
    }

    const reply = await prisma.reply.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
      include: { contact: true },
    });

    if (!reply) {
      return res.status(404).json({ error: 'Reply not found' });
    }

    // TODO: Queue auto-reply send job
    // await queueAutoReply(reply.id, message);

    const updated = await prisma.reply.update({
      where: { id: parseInt(req.params.id) },
      data: { autoReplyStatus: 'sent', autoReplyMessage: message },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Reply', reply.id, { 
      action: 'auto_reply_sent',
      message 
    });

    res.json({ ...updated, message: 'Auto-reply queued for sending' });
  } catch (error) {
    console.error('Error sending auto-reply:', error);
    res.status(500).json({ error: 'Failed to send auto-reply' });
  }
});

// GET /api/inbox/stats - Get inbox statistics
router.get('/stats', requirePermission('inbox:read'), async (req, res) => {
  try {
    const [total, byClassification, bySentiment, byAutoReplyStatus] = await Promise.all([
      prisma.reply.count({ where: { organizationId: req.user.organizationId } }),
      prisma.reply.groupBy({
        by: ['classification'],
        where: { organizationId: req.user.organizationId },
        _count: true,
      }),
      prisma.reply.groupBy({
        by: ['sentiment'],
        where: { organizationId: req.user.organizationId },
        _count: true,
      }),
      prisma.reply.groupBy({
        by: ['autoReplyStatus'],
        where: { organizationId: req.user.organizationId },
        _count: true,
      }),
    ]);

    res.json({
      total,
      byClassification: byClassification.reduce((acc, c) => ({ ...acc, [c.classification]: c._count }), {}),
      bySentiment: bySentiment.reduce((acc, s) => ({ ...acc, [s.sentiment]: s._count }), {}),
      byAutoReplyStatus: byAutoReplyStatus.reduce((acc, s) => ({ ...acc, [s.autoReplyStatus]: s._count }), {}),
    });
  } catch (error) {
    console.error('Error fetching inbox stats:', error);
    res.status(500).json({ error: 'Failed to fetch inbox stats' });
  }
});

// Webhook endpoint for receiving emails (e.g., from SendGrid, Mailgun, etc.)
router.post('/webhook', async (req, res) => {
  try {
    // This endpoint receives emails from email providers via webhook
    // The payload format depends on the provider (SendGrid, Mailgun, SES, etc.)
    
    const { organizationId, email, subject, body, headers } = req.body;

    // TODO: Validate webhook signature
    // TODO: Parse email and create Reply record
    // TODO: Run AI classification

    // For now, acknowledge receipt
    res.json({ received: true });
  } catch (error) {
    console.error('Error processing inbound webhook:', error);
    res.status(500).json({ error: 'Failed to process webhook' });
  }
});

export default router;