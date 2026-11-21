import express from 'express';
import { PrismaClient } from '@prisma/client';
import { requirePermission } from '../middleware/rbac.js';
import { auditLog } from '../middleware/auditLog.js';

const prisma = new PrismaClient();
const router = express.Router();

// GET /api/verifications - List email verifications
router.get('/', requirePermission('contacts:verify'), async (req, res) => {
  try {
    const { page = 1, limit = 50, status, search } = req.query;

    const where = {
      organizationId: req.user.organizationId,
    };

    if (status) where.status = status;
    if (search) {
      where.email = { contains: search, mode: 'insensitive' };
    }

    const [verifications, total] = await Promise.all([
      prisma.emailVerification.findMany({
        where,
        skip: (page - 1) * limit,
        take: parseInt(limit),
        orderBy: { createdAt: 'desc' },
        include: { contact: { select: { id: true, email: true, name: true } } },
      }),
      prisma.emailVerification.count({ where }),
    ]);

    res.json({
      verifications,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    console.error('Error fetching verifications:', error);
    res.status(500).json({ error: 'Failed to fetch verifications' });
  }
});

// GET /api/verifications/stats - Get verification statistics
router.get('/stats', requirePermission('contacts:verify'), async (req, res) => {
  try {
    const stats = await prisma.emailVerification.groupBy({
      by: ['status'],
      where: { organizationId: req.user.organizationId },
      _count: true,
    });

    const total = await prisma.emailVerification.count({
      where: { organizationId: req.user.organizationId },
    });

    const valid = await prisma.emailVerification.count({
      where: { organizationId: req.user.organizationId, status: 'valid' },
    });

    const invalid = await prisma.emailVerification.count({
      where: { organizationId: req.user.organizationId, status: 'invalid' },
    });

    const risky = await prisma.emailVerification.count({
      where: { organizationId: req.user.organizationId, status: 'risky' },
    });

    res.json({
      total,
      valid,
      invalid,
      risky,
      byStatus: stats.reduce((acc, s) => ({ ...acc, [s.status]: s._count }), {}),
    });
  } catch (error) {
    console.error('Error fetching verification stats:', error);
    res.status(500).json({ error: 'Failed to fetch verification stats' });
  }
});

// POST /api/verifications - Verify single email
router.post('/', requirePermission('contacts:verify'), async (req, res) => {
  try {
    const { email } = req.body;

    if (!email) {
      return res.status(400).json({ error: 'Email is required' });
    }

    // Check if already verified recently
    const existing = await prisma.emailVerification.findUnique({
      where: { email },
    });

    if (existing && existing.lastChecked && (Date.now() - new Date(existing.lastChecked).getTime()) < 24 * 60 * 60 * 1000) {
      return res.json({ ...existing, cached: true });
    }

    // TODO: Implement actual email verification (SMTP check, MX lookup, etc.)
    // For now, return mock result
    const result = {
      email,
      status: 'valid',
      smtpCheck: 'valid',
      mxCheck: 'valid',
      catchAll: false,
      disposable: false,
      domain: email.split('@')[1],
      lastChecked: new Date(),
    };

    const verification = await prisma.emailVerification.upsert({
      where: { email },
      create: {
        ...result,
        organizationId: req.user.organizationId,
      },
      update: {
        ...result,
        organizationId: req.user.organizationId,
      },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'EmailVerification', verification.id, { email });

    res.json(verification);
  } catch (error) {
    console.error('Error verifying email:', error);
    res.status(500).json({ error: 'Failed to verify email' });
  }
});

// POST /api/verifications/bulk - Verify multiple emails
router.post('/bulk', requirePermission('contacts:verify'), async (req, res) => {
  try {
    const { emails } = req.body;

    if (!emails || !Array.isArray(emails) || emails.length === 0) {
      return res.status(400).json({ error: 'Emails array is required' });
    }

    if (emails.length > 1000) {
      return res.status(400).json({ error: 'Maximum 1000 emails per request' });
    }

    // TODO: Queue bulk verification job
    // For now, process synchronously with mock results
    const results = await Promise.all(
      emails.map(async (email) => {
        const existing = await prisma.emailVerification.findUnique({ where: { email } });
        if (existing && existing.lastChecked && (Date.now() - new Date(existing.lastChecked).getTime()) < 24 * 60 * 60 * 1000) {
          return { ...existing, cached: true };
        }

        const result = {
          email,
          status: 'valid',
          smtpCheck: 'valid',
          mxCheck: 'valid',
          catchAll: false,
          disposable: false,
          domain: email.split('@')[1],
          lastChecked: new Date(),
        };

        return prisma.emailVerification.upsert({
          where: { email },
          create: { ...result, organizationId: req.user.organizationId },
          update: { ...result, organizationId: req.user.organizationId },
        });
      })
    );

    await auditLog.create(req.user.organizationId, req.user.id, 'EmailVerification', null, { 
      action: 'bulk_verified',
      count: results.length 
    });

    res.json({ verifications: results });
  } catch (error) {
    console.error('Error bulk verifying emails:', error);
    res.status(500).json({ error: 'Failed to bulk verify emails' });
  }
});

// POST /api/verifications/contacts/:contactId - Verify contact's email
router.post('/contacts/:contactId', requirePermission('contacts:verify'), async (req, res) => {
  try {
    const contact = await prisma.contact.findFirst({
      where: { id: parseInt(req.params.contactId), organizationId: req.user.organizationId },
    });

    if (!contact) {
      return res.status(404).json({ error: 'Contact not found' });
    }

    const existing = await prisma.emailVerification.findUnique({
      where: { email: contact.email },
    });

    if (existing && existing.lastChecked && (Date.now() - new Date(existing.lastChecked).getTime()) < 24 * 60 * 60 * 1000) {
      // Update contact's eligibleToEmail based on verification
      await prisma.contact.update({
        where: { id: contact.id },
        data: { eligibleToEmail: existing.status === 'valid' },
      });
      return res.json({ ...existing, cached: true });
    }

    // TODO: Actual verification
    const result = {
      email: contact.email,
      status: 'valid',
      smtpCheck: 'valid',
      mxCheck: 'valid',
      catchAll: false,
      disposable: false,
      domain: contact.email.split('@')[1],
      lastChecked: new Date(),
      contactId: contact.id,
    };

    const verification = await prisma.emailVerification.upsert({
      where: { email: contact.email },
      create: { ...result, organizationId: req.user.organizationId },
      update: { ...result, organizationId: req.user.organizationId },
    });

    // Update contact
    await prisma.contact.update({
      where: { id: contact.id },
      data: { eligibleToEmail: result.status === 'valid' },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'EmailVerification', verification.id, { 
      email: contact.email,
      contactId: contact.id 
    });

    res.json(verification);
  } catch (error) {
    console.error('Error verifying contact email:', error);
    res.status(500).json({ error: 'Failed to verify contact email' });
  }
});

export default router;