import express from 'express';
import { PrismaClient } from '@prisma/client';
import { requirePermission } from '../middleware/rbac.js';
import { auditLog } from '../middleware/auditLog.js';

const prisma = new PrismaClient();
const router = express.Router();

// GET /api/drafts - List drafts
router.get('/', requirePermission('campaigns:read'), async (req, res) => {
  try {
    const { page = 1, limit = 50, status, contactId } = req.query;

    const where = {
      organizationId: req.user.organizationId,
    };

    if (status) where.status = status;
    if (contactId) where.contactId = parseInt(contactId);

    const [drafts, total] = await Promise.all([
      prisma.draft.findMany({
        where,
        skip: (page - 1) * limit,
        take: parseInt(limit),
        orderBy: { createdAt: 'desc' },
        include: { contact: { select: { id: true, email: true, name: true } } },
      }),
      prisma.draft.count({ where }),
    ]);

    res.json({
      drafts,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    console.error('Error fetching drafts:', error);
    res.status(500).json({ error: 'Failed to fetch drafts' });
  }
});

// GET /api/drafts/:id - Get single draft
router.get('/:id', requirePermission('campaigns:read'), async (req, res) => {
  try {
    const draft = await prisma.draft.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
      include: { contact: { select: { id: true, email: true, name: true, customFields: true } } },
    });

    if (!draft) {
      return res.status(404).json({ error: 'Draft not found' });
    }

    res.json(draft);
  } catch (error) {
    console.error('Error fetching draft:', error);
    res.status(500).json({ error: 'Failed to fetch draft' });
  }
});

// POST /api/drafts - Create draft
router.post('/', requirePermission('campaigns:write'), async (req, res) => {
  try {
    const { subject, body, contactId, variables, priority = 'normal' } = req.body;

    if (!subject || !body) {
      return res.status(400).json({ error: 'Subject and body are required' });
    }

    const draft = await prisma.draft.create({
      data: {
        subject,
        body,
        status: 'draft',
        contactId: contactId ? parseInt(contactId) : null,
        variables: variables || {},
        priority,
        organizationId: req.user.organizationId,
      },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Draft', draft.id, { subject });

    res.status(201).json(draft);
  } catch (error) {
    console.error('Error creating draft:', error);
    res.status(500).json({ error: 'Failed to create draft' });
  }
});

// PUT /api/drafts/:id - Update draft
router.put('/:id', requirePermission('campaigns:write'), async (req, res) => {
  try {
    const { subject, body, status, variables, priority } = req.body;

    const existing = await prisma.draft.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!existing) {
      return res.status(404).json({ error: 'Draft not found' });
    }

    const draft = await prisma.draft.update({
      where: { id: parseInt(req.params.id) },
      data: { subject, body, status, variables, priority },
    });

    await auditLog.update(req.user.organizationId, req.user.id, 'Draft', draft.id, { subject });

    res.json(draft);
  } catch (error) {
    console.error('Error updating draft:', error);
    res.status(500).json({ error: 'Failed to update draft' });
  }
});

// DELETE /api/drafts/:id - Delete draft
router.delete('/:id', requirePermission('campaigns:delete'), async (req, res) => {
  try {
    const existing = await prisma.draft.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!existing) {
      return res.status(404).json({ error: 'Draft not found' });
    }

    await prisma.draft.delete({ where: { id: parseInt(req.params.id) } });

    await auditLog.delete(req.user.organizationId, req.user.id, 'Draft', req.params.id, { subject: existing.subject });

    res.json({ message: 'Draft deleted successfully' });
  } catch (error) {
    console.error('Error deleting draft:', error);
    res.status(500).json({ error: 'Failed to delete draft' });
  }
});

// POST /api/drafts/:id/approve - Approve draft for sending
router.post('/:id/approve', requirePermission('campaigns:write'), async (req, res) => {
  try {
    const draft = await prisma.draft.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!draft) {
      return res.status(404).json({ error: 'Draft not found' });
    }

    const updated = await prisma.draft.update({
      where: { id: parseInt(req.params.id) },
      data: { status: 'approved' },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Draft', draft.id, { 
      action: 'approved',
      subject: draft.subject 
    });

    res.json(updated);
  } catch (error) {
    console.error('Error approving draft:', error);
    res.status(500).json({ error: 'Failed to approve draft' });
  }
});

// POST /api/drafts/:id/send - Send draft immediately
router.post('/:id/send', requirePermission('campaigns:send'), async (req, res) => {
  try {
    const draft = await prisma.draft.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
      include: { contact: true },
    });

    if (!draft) {
      return res.status(404).json({ error: 'Draft not found' });
    }

    if (!draft.contactId) {
      return res.status(400).json({ error: 'Draft must have a contact to send' });
    }

    if (draft.status === 'sent') {
      return res.status(400).json({ error: 'Draft already sent' });
    }

    // TODO: Queue email send job
    // await queueEmailSend(draft.id);

    const updated = await prisma.draft.update({
      where: { id: parseInt(req.params.id) },
      data: { status: 'sending', sentAt: new Date() },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Draft', draft.id, { 
      action: 'sent',
      subject: draft.subject 
    });

    res.json({ ...updated, message: 'Draft queued for sending' });
  } catch (error) {
    console.error('Error sending draft:', error);
    res.status(500).json({ error: 'Failed to send draft' });
  }
});

// POST /api/drafts/bulk-create - Create drafts from campaign
router.post('/bulk-create', requirePermission('campaigns:write'), async (req, res) => {
  try {
    const { campaignId, contactIds, subjectTemplate, bodyTemplate, variables } = req.body;

    if (!campaignId || !contactIds || !Array.isArray(contactIds)) {
      return res.status(400).json({ error: 'campaignId and contactIds array are required' });
    }

    const campaign = await prisma.campaign.findFirst({
      where: { id: parseInt(campaignId), organizationId: req.user.organizationId },
      include: { template: true },
    });

    if (!campaign) {
      return res.status(404).json({ error: 'Campaign not found' });
    }

    const contacts = await prisma.contact.findMany({
      where: {
        id: { in: contactIds.map(id => parseInt(id)) },
        organizationId: req.user.organizationId,
        eligibleToEmail: true,
      },
    });

    const drafts = await Promise.all(
      contacts.map(contact =>
        prisma.draft.create({
          data: {
            subject: subjectTemplate || campaign.template?.subjectTemplate || '',
            body: bodyTemplate || campaign.template?.bodyTemplate || '',
            status: 'draft',
            contactId: contact.id,
            variables: { ...campaign.template?.variables, ...variables, contact },
            priority: 'normal',
            organizationId: req.user.organizationId,
          },
        })
      )
    );

    await auditLog.create(req.user.organizationId, req.user.id, 'Draft', null, { 
      action: 'bulk_created',
      campaignId,
      count: drafts.length 
    });

    res.status(201).json({ drafts, count: drafts.length });
  } catch (error) {
    console.error('Error bulk creating drafts:', error);
    res.status(500).json({ error: 'Failed to create drafts' });
  }
});

export default router;