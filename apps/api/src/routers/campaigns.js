import express from 'express';
import { PrismaClient } from '@prisma/client';
import { requirePermission } from '../middleware/rbac.js';
import { auditLog } from '../middleware/auditLog.js';
import { rateLimiters } from '../middleware/rateLimit.js';

const prisma = new PrismaClient();
const router = express.Router();

// GET /api/campaigns - List campaigns
router.get('/', requirePermission('campaigns:read'), async (req, res) => {
  try {
    const { 
      page = 1, 
      limit = 20, 
      search, 
      status, 
      type,
      sortBy = 'createdAt',
      sortOrder = 'desc'
    } = req.query;

    const where = {
      organizationId: req.user.organizationId,
    };

    if (search) {
      where.OR = [
        { name: { contains: search, mode: 'insensitive' } },
        { description: { contains: search, mode: 'insensitive' } },
      ];
    }

    if (status) where.status = status;
    if (type) where.type = type;

    const [campaigns, total] = await Promise.all([
      prisma.campaign.findMany({
        where,
        skip: (page - 1) * limit,
        take: parseInt(limit),
        orderBy: { [sortBy]: sortOrder },
        include: {
          template: { select: { id: true, name: true, category: true } },
          targetSegment: { select: { id: true, name: true } },
          createdBy: { select: { id: true, name: true, email: true } },
          _count: {
            select: { followUps: true },
          },
        },
      }),
      prisma.campaign.count({ where }),
    ]);

    res.json({
      campaigns,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    console.error('Error fetching campaigns:', error);
    res.status(500).json({ error: 'Failed to fetch campaigns' });
  }
});

// GET /api/campaigns/:id - Get single campaign with stats
router.get('/:id', requirePermission('campaigns:read'), async (req, res) => {
  try {
    const campaign = await prisma.campaign.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
      include: {
        template: true,
        targetSegment: true,
        createdBy: { select: { id: true, name: true, email: true } },
        followUps: {
          orderBy: { stage: 'asc' },
          include: { contact: { select: { id: true, email: true, name: true } } },
        },
        abTestConfig: true,
      },
    });

    if (!campaign) {
      return res.status(404).json({ error: 'Campaign not found' });
    }

    // Calculate rates
    const delivered = campaign.delivered || 0;
    const rates = {
      openRate: delivered > 0 ? ((campaign.opened || 0) / delivered * 100).toFixed(2) : 0,
      clickRate: delivered > 0 ? ((campaign.clicked || 0) / delivered * 100).toFixed(2) : 0,
      replyRate: delivered > 0 ? ((campaign.replied || 0) / delivered * 100).toFixed(2) : 0,
      bounceRate: delivered > 0 ? ((campaign.bounced || 0) / delivered * 100).toFixed(2) : 0,
      unsubscribeRate: delivered > 0 ? ((campaign.unsubscribed || 0) / delivered * 100).toFixed(2) : 0,
    };

    res.json({ ...campaign, rates });
  } catch (error) {
    console.error('Error fetching campaign:', error);
    res.status(500).json({ error: 'Failed to fetch campaign' });
  }
});

// POST /api/campaigns - Create campaign
router.post('/', requirePermission('campaigns:write'), async (req, res) => {
  try {
    const { 
      name, 
      description, 
      type = 'regular',
      templateId, 
      targetSegmentId, 
      abTestConfig,
      scheduledAt,
      settings
    } = req.body;

    if (!name) {
      return res.status(400).json({ error: 'Campaign name is required' });
    }

    const campaign = await prisma.campaign.create({
      data: {
        name,
        description,
        type,
        templateId: templateId ? parseInt(templateId) : null,
        targetSegmentId: targetSegmentId ? parseInt(targetSegmentId) : null,
        abTestConfig,
        scheduledAt: scheduledAt ? new Date(scheduledAt) : null,
        organizationId: req.user.organizationId,
        createdById: req.user.id,
        status: 'draft',
      },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Campaign', campaign.id, { name });

    res.status(201).json(campaign);
  } catch (error) {
    console.error('Error creating campaign:', error);
    res.status(500).json({ error: 'Failed to create campaign' });
  }
});

// PUT /api/campaigns/:id - Update campaign
router.put('/:id', requirePermission('campaigns:write'), async (req, res) => {
  try {
    const { 
      name, 
      description, 
      type,
      templateId, 
      targetSegmentId, 
      abTestConfig,
      scheduledAt,
      status
    } = req.body;

    const existing = await prisma.campaign.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!existing) {
      return res.status(404).json({ error: 'Campaign not found' });
    }

    // Prevent modification of sent campaigns
    if (existing.status === 'sent' && status !== 'sent') {
      return res.status(400).json({ error: 'Cannot modify a sent campaign' });
    }

    const campaign = await prisma.campaign.update({
      where: { id: parseInt(req.params.id) },
      data: {
        name,
        description,
        type,
        templateId: templateId ? parseInt(templateId) : null,
        targetSegmentId: targetSegmentId ? parseInt(targetSegmentId) : null,
        abTestConfig,
        scheduledAt: scheduledAt ? new Date(scheduledAt) : null,
        status,
      },
    });

    await auditLog.update(req.user.organizationId, req.user.id, 'Campaign', campaign.id, { name });

    res.json(campaign);
  } catch (error) {
    console.error('Error updating campaign:', error);
    res.status(500).json({ error: 'Failed to update campaign' });
  }
});

// DELETE /api/campaigns/:id - Delete campaign
router.delete('/:id', requirePermission('campaigns:delete'), async (req, res) => {
  try {
    const existing = await prisma.campaign.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!existing) {
      return res.status(404).json({ error: 'Campaign not found' });
    }

    if (existing.status === 'sent') {
      return res.status(400).json({ error: 'Cannot delete a sent campaign' });
    }

    await prisma.campaign.delete({ where: { id: parseInt(req.params.id) } });

    await auditLog.delete(req.user.organizationId, req.user.id, 'Campaign', req.params.id, { name: existing.name });

    res.json({ message: 'Campaign deleted successfully' });
  } catch (error) {
    console.error('Error deleting campaign:', error);
    res.status(500).json({ error: 'Failed to delete campaign' });
  }
});

// POST /api/campaigns/:id/schedule - Schedule campaign
router.post('/:id/schedule', requirePermission('campaigns:send'), async (req, res) => {
  try {
    const { scheduledAt } = req.body;

    if (!scheduledAt) {
      return res.status(400).json({ error: 'scheduledAt is required' });
    }

    const campaign = await prisma.campaign.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!campaign) {
      return res.status(404).json({ error: 'Campaign not found' });
    }

    if (campaign.status !== 'draft' && campaign.status !== 'scheduled') {
      return res.status(400).json({ error: 'Can only schedule draft or scheduled campaigns' });
    }

    const updated = await prisma.campaign.update({
      where: { id: parseInt(req.params.id) },
      data: {
        scheduledAt: new Date(scheduledAt),
        status: 'scheduled',
      },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Campaign', campaign.id, { 
      action: 'scheduled',
      scheduledAt 
    });

    // TODO: Add job to queue for sending at scheduledAt

    res.json(updated);
  } catch (error) {
    console.error('Error scheduling campaign:', error);
    res.status(500).json({ error: 'Failed to schedule campaign' });
  }
});

// POST /api/campaigns/:id/send - Send campaign immediately
router.post('/:id/send', requirePermission('campaigns:send'), rateLimiters.campaignSend, async (req, res) => {
  try {
    const campaign = await prisma.campaign.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
      include: { template: true, targetSegment: true },
    });

    if (!campaign) {
      return res.status(404).json({ error: 'Campaign not found' });
    }

    if (campaign.status === 'sent') {
      return res.status(400).json({ error: 'Campaign already sent' });
    }

    if (campaign.status === 'sending') {
      return res.status(400).json({ error: 'Campaign is already sending' });
    }

    // Validate campaign has required data
    if (!campaign.templateId) {
      return res.status(400).json({ error: 'Campaign must have a template' });
    }

    const updated = await prisma.campaign.update({
      where: { id: parseInt(req.params.id) },
      data: { status: 'sending', sentAt: new Date() },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Campaign', campaign.id, { 
      action: 'sent' 
    });

    // TODO: Queue campaign send job
    // await queueCampaignSend(campaign.id);

    res.json({ ...updated, message: 'Campaign queued for sending' });
  } catch (error) {
    console.error('Error sending campaign:', error);
    res.status(500).json({ error: 'Failed to send campaign' });
  }
});

// POST /api/campaigns/:id/approve - Approve campaign
router.post('/:id/approve', requirePermission('campaigns:approve'), async (req, res) => {
  try {
    const campaign = await prisma.campaign.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!campaign) {
      return res.status(404).json({ error: 'Campaign not found' });
    }

    if (campaign.status !== 'pending_approval') {
      return res.status(400).json({ error: 'Campaign is not pending approval' });
    }

    const updated = await prisma.campaign.update({
      where: { id: parseInt(req.params.id) },
      data: { status: 'approved' },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Campaign', campaign.id, { 
      action: 'approved' 
    });

    res.json(updated);
  } catch (error) {
    console.error('Error approving campaign:', error);
    res.status(500).json({ error: 'Failed to approve campaign' });
  }
});

// POST /api/campaigns/:id/reject - Reject campaign
router.post('/:id/reject', requirePermission('campaigns:approve'), async (req, res) => {
  try {
    const { reason } = req.body;
    const campaign = await prisma.campaign.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!campaign) {
      return res.status(404).json({ error: 'Campaign not found' });
    }

    if (campaign.status !== 'pending_approval') {
      return res.status(400).json({ error: 'Campaign is not pending approval' });
    }

    const updated = await prisma.campaign.update({
      where: { id: parseInt(req.params.id) },
      data: { status: 'rejected' },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Campaign', campaign.id, { 
      action: 'rejected',
      reason 
    });

    res.json(updated);
  } catch (error) {
    console.error('Error rejecting campaign:', error);
    res.status(500).json({ error: 'Failed to reject campaign' });
  }
});

// GET /api/campaigns/:id/stats - Get campaign statistics
router.get('/:id/stats', requirePermission('campaigns:read'), async (req, res) => {
  try {
    const campaign = await prisma.campaign.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!campaign) {
      return res.status(404).json({ error: 'Campaign not found' });
    }

    // Get detailed stats from events
    const events = await prisma.event.groupBy({
      by: ['type'],
      where: {
        organizationId: req.user.organizationId,
        payload: {
          path: ['campaignId'],
          equals: campaign.id,
        },
      },
      _count: true,
    });

    const stats = {
      sent: campaign.delivered || 0,
      delivered: campaign.delivered || 0,
      opened: campaign.opened || 0,
      clicked: campaign.clicked || 0,
      replied: campaign.replied || 0,
      bounced: campaign.bounced || 0,
      unsubscribed: campaign.unsubscribed || 0,
      events: events.reduce((acc, e) => ({ ...acc, [e.type]: e._count }), {}),
    };

    res.json(stats);
  } catch (error) {
    console.error('Error fetching campaign stats:', error);
    res.status(500).json({ error: 'Failed to fetch campaign stats' });
  }
});

export default router;