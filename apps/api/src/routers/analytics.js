import express from 'express';
import { PrismaClient } from '@prisma/client';
import { requirePermission } from '../middleware/rbac.js';

const prisma = new PrismaClient();
const router = express.Router();

// GET /api/analytics/overview - Get overview metrics
router.get('/overview', requirePermission('analytics:read'), async (req, res) => {
  try {
    const { startDate, endDate } = req.query;
    
    const dateFilter = {};
    if (startDate) dateFilter.gte = new Date(startDate);
    if (endDate) dateFilter.lte = new Date(endDate);

    const where = {
      organizationId: req.user.organizationId,
      ...(Object.keys(dateFilter).length > 0 && { createdAt: dateFilter }),
    };

    // Get campaign stats
    const campaigns = await prisma.campaign.findMany({
      where: { organizationId: req.user.organizationId },
      select: { delivered: true, opened: true, clicked: true, replied: true, bounced: true, unsubscribed: true, status: true },
    });

    const totals = campaigns.reduce((acc, c) => ({
      sent: acc.sent + (c.delivered || 0),
      delivered: acc.delivered + (c.delivered || 0),
      opened: acc.opened + (c.opened || 0),
      clicked: acc.clicked + (c.clicked || 0),
      replied: acc.replied + (c.replied || 0),
      bounced: acc.bounced + (c.bounced || 0),
      unsubscribed: acc.unsubscribed + (c.unsubscribed || 0),
    }), { sent: 0, delivered: 0, opened: 0, clicked: 0, replied: 0, bounced: 0, unsubscribed: 0 });

    const rates = totals.delivered > 0 ? {
      deliveryRate: ((totals.delivered / totals.sent) * 100).toFixed(2),
      openRate: ((totals.opened / totals.delivered) * 100).toFixed(2),
      clickRate: ((totals.clicked / totals.delivered) * 100).toFixed(2),
      replyRate: ((totals.replied / totals.delivered) * 100).toFixed(2),
      bounceRate: ((totals.bounced / totals.delivered) * 100).toFixed(2),
      unsubscribeRate: ((totals.unsubscribed / totals.delivered) * 100).toFixed(2),
    } : {
      deliveryRate: 0, openRate: 0, clickRate: 0, replyRate: 0, bounceRate: 0, unsubscribeRate: 0,
    };

    // Campaigns by status
    const campaignsByStatus = campaigns.reduce((acc, c) => {
      acc[c.status] = (acc[c.status] || 0) + 1;
      return acc;
    }, {});

    // Contact growth
    const contactCount = await prisma.contact.count({ where: { organizationId: req.user.organizationId } });
    const newContactsThisMonth = await prisma.contact.count({
      where: {
        organizationId: req.user.organizationId,
        createdAt: { gte: new Date(new Date().setDate(1)) },
      },
    });

    res.json({
      totals,
      rates,
      campaignsByStatus,
      contacts: { total: contactCount, newThisMonth: newContactsThisMonth },
    });
  } catch (error) {
    console.error('Error fetching analytics overview:', error);
    res.status(500).json({ error: 'Failed to fetch analytics overview' });
  }
});

// GET /api/analytics/campaigns - Get campaign performance over time
router.get('/campaigns', requirePermission('analytics:read'), async (req, res) => {
  try {
    const { startDate, endDate, interval = 'day' } = req.query;

    // TODO: Implement time-series aggregation
    // For now, return campaign list with stats
    const campaigns = await prisma.campaign.findMany({
      where: { organizationId: req.user.organizationId },
      orderBy: { sentAt: 'desc' },
      take: 50,
      select: {
        id: true,
        name: true,
        status: true,
        sentAt: true,
        delivered: true,
        opened: true,
        clicked: true,
        replied: true,
        bounced: true,
        unsubscribed: true,
      },
    });

    const campaignStats = campaigns.map(c => ({
      ...c,
      deliveryRate: c.sent > 0 ? ((c.delivered / c.sent) * 100).toFixed(2) : 0,
      openRate: c.delivered > 0 ? ((c.opened / c.delivered) * 100).toFixed(2) : 0,
      clickRate: c.delivered > 0 ? ((c.clicked / c.delivered) * 100).toFixed(2) : 0,
      replyRate: c.delivered > 0 ? ((c.replied / c.delivered) * 100).toFixed(2) : 0,
    }));

    res.json({ campaigns: campaignStats });
  } catch (error) {
    console.error('Error fetching campaign analytics:', error);
    res.status(500).json({ error: 'Failed to fetch campaign analytics' });
  }
});

// GET /api/analytics/events - Get event timeline
router.get('/events', requirePermission('analytics:read'), async (req, res) => {
  try {
    const { page = 1, limit = 100, type, contactId, campaignId } = req.query;

    const where = { organizationId: req.user.organizationId };
    if (type) where.type = type;
    if (contactId) where.contactId = parseInt(contactId);
    if (campaignId) {
      where.payload = { path: ['campaignId'], equals: parseInt(campaignId) };
    }

    const [events, total] = await Promise.all([
      prisma.event.findMany({
        where,
        skip: (page - 1) * limit,
        take: parseInt(limit),
        orderBy: { createdAt: 'desc' },
        include: { contact: { select: { id: true, email: true, name: true } } },
      }),
      prisma.event.count({ where }),
    ]);

    res.json({
      events,
      pagination: { page: parseInt(page), limit: parseInt(limit), total, totalPages: Math.ceil(total / limit) },
    });
  } catch (error) {
    console.error('Error fetching events:', error);
    res.status(500).json({ error: 'Failed to fetch events' });
  }
});

// GET /api/analytics/deliverability - Get deliverability metrics
router.get('/deliverability', requirePermission('analytics:read'), async (req, res) => {
  try {
    // TODO: Implement deliverability tracking (bounces, complaints, spam reports)
    // This would integrate with email provider webhooks

    res.json({
      bounces: { hard: 0, soft: 0 },
      complaints: 0,
      spamReports: 0,
      suppressionList: 0,
      reputationScore: 95,
    });
  } catch (error) {
    console.error('Error fetching deliverability:', error);
    res.status(500).json({ error: 'Failed to fetch deliverability metrics' });
  }
});

// GET /api/analytics/engagement - Get engagement heatmap
router.get('/engagement', requirePermission('analytics:read'), async (req, res) => {
  try {
    // TODO: Implement engagement heatmap (opens/clicks by hour/day)
    res.json({
      hourlyOpens: Array(24).fill(0),
      hourlyClicks: Array(24).fill(0),
      dailyOpens: Array(7).fill(0),
      dailyClicks: Array(7).fill(0),
    });
  } catch (error) {
    console.error('Error fetching engagement:', error);
    res.status(500).json({ error: 'Failed to fetch engagement data' });
  }
});

// GET /api/analytics/export - Export analytics data
router.get('/export', requirePermission('analytics:export'), async (req, res) => {
  try {
    const { type = 'campaigns', format = 'csv', startDate, endDate } = req.query;

    // TODO: Implement export functionality
    res.json({ message: 'Export functionality coming soon', type, format });
  } catch (error) {
    console.error('Error exporting analytics:', error);
    res.status(500).json({ error: 'Failed to export analytics' });
  }
});

export default router;