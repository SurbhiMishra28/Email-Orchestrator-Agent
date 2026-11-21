import express from 'express';
import { PrismaClient } from '@prisma/client';
import { requirePermission } from '../middleware/rbac.js';
import { auditLog } from '../middleware/auditLog.js';

const prisma = new PrismaClient();
const router = express.Router();

// GET /api/segments - List segments
router.get('/', requirePermission('segments:read'), async (req, res) => {
  try {
    const { page = 1, limit = 20, search } = req.query;

    const where = {
      organizationId: req.user.organizationId,
    };

    if (search) {
      where.OR = [
        { name: { contains: search, mode: 'insensitive' } },
        { description: { contains: search, mode: 'insensitive' } },
      ];
    }

    const [segments, total] = await Promise.all([
      prisma.segment.findMany({
        where,
        skip: (page - 1) * limit,
        take: parseInt(limit),
        orderBy: { createdAt: 'desc' },
        include: {
          _count: { select: { contacts: true } },
          campaigns: { select: { id: true, name: true, status: true } },
        },
      }),
      prisma.segment.count({ where }),
    ]);

    res.json({
      segments,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    console.error('Error fetching segments:', error);
    res.status(500).json({ error: 'Failed to fetch segments' });
  }
});

// GET /api/segments/:id - Get segment with contacts
router.get('/:id', requirePermission('segments:read'), async (req, res) => {
  try {
    const { page = 1, limit = 50 } = req.query;

    const segment = await prisma.segment.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
      include: {
        contacts: {
          skip: (page - 1) * limit,
          take: parseInt(limit),
          include: { contact: true },
          orderBy: { addedAt: 'desc' },
        },
        _count: { select: { contacts: true } },
        campaigns: { select: { id: true, name: true, status: true } },
      },
    });

    if (!segment) {
      return res.status(404).json({ error: 'Segment not found' });
    }

    const totalContacts = await prisma.segmentContact.count({
      where: { segmentId: segment.id },
    });

    res.json({
      ...segment,
      contacts: segment.contacts.map(sc => sc.contact),
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total: totalContacts,
        totalPages: Math.ceil(totalContacts / limit),
      },
    });
  } catch (error) {
    console.error('Error fetching segment:', error);
    res.status(500).json({ error: 'Failed to fetch segment' });
  }
});

// POST /api/segments - Create segment
router.post('/', requirePermission('segments:write'), async (req, res) => {
  try {
    const { name, description, query } = req.body;

    if (!name || !query) {
      return res.status(400).json({ error: 'Name and query are required' });
    }

    const segment = await prisma.segment.create({
      data: {
        name,
        description,
        query,
        organizationId: req.user.organizationId,
      },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Segment', segment.id, { name });

    // TODO: Queue segment refresh job to populate contacts
    // await queueSegmentRefresh(segment.id);

    res.status(201).json(segment);
  } catch (error) {
    console.error('Error creating segment:', error);
    res.status(500).json({ error: 'Failed to create segment' });
  }
});

// PUT /api/segments/:id - Update segment
router.put('/:id', requirePermission('segments:write'), async (req, res) => {
  try {
    const { name, description, query } = req.body;

    const existing = await prisma.segment.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!existing) {
      return res.status(404).json({ error: 'Segment not found' });
    }

    const segment = await prisma.segment.update({
      where: { id: parseInt(req.params.id) },
      data: { name, description, query },
    });

    await auditLog.update(req.user.organizationId, req.user.id, 'Segment', segment.id, { name });

    // TODO: Queue segment refresh if query changed
    // if (query && query !== existing.query) await queueSegmentRefresh(segment.id);

    res.json(segment);
  } catch (error) {
    console.error('Error updating segment:', error);
    res.status(500).json({ error: 'Failed to update segment' });
  }
});

// DELETE /api/segments/:id - Delete segment
router.delete('/:id', requirePermission('segments:delete'), async (req, res) => {
  try {
    const existing = await prisma.segment.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!existing) {
      return res.status(404).json({ error: 'Segment not found' });
    }

    await prisma.segment.delete({ where: { id: parseInt(req.params.id) } });

    await auditLog.delete(req.user.organizationId, req.user.id, 'Segment', req.params.id, { name: existing.name });

    res.json({ message: 'Segment deleted successfully' });
  } catch (error) {
    console.error('Error deleting segment:', error);
    res.status(500).json({ error: 'Failed to delete segment' });
  }
});

// POST /api/segments/:id/refresh - Refresh segment contacts
router.post('/:id/refresh', requirePermission('segments:write'), async (req, res) => {
  try {
    const segment = await prisma.segment.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!segment) {
      return res.status(404).json({ error: 'Segment not found' });
    }

    // TODO: Implement segment refresh logic
    // This would evaluate the query against all contacts and update SegmentContact records
    // For now, return a placeholder response

    await auditLog.create(req.user.organizationId, req.user.id, 'Segment', segment.id, { 
      action: 'refreshed' 
    });

    res.json({ message: 'Segment refresh queued', segmentId: segment.id });
  } catch (error) {
    console.error('Error refreshing segment:', error);
    res.status(500).json({ error: 'Failed to refresh segment' });
  }
});

// POST /api/segments/:id/contacts - Add contacts to segment manually
router.post('/:id/contacts', requirePermission('segments:write'), async (req, res) => {
  try {
    const { contactIds } = req.body;

    if (!contactIds || !Array.isArray(contactIds) || contactIds.length === 0) {
      return res.status(400).json({ error: 'contactIds array is required' });
    }

    const segment = await prisma.segment.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!segment) {
      return res.status(404).json({ error: 'Segment not found' });
    }

    // Verify all contacts belong to the organization
    const contacts = await prisma.contact.findMany({
      where: {
        id: { in: contactIds.map(id => parseInt(id)) },
        organizationId: req.user.organizationId,
      },
    });

    if (contacts.length !== contactIds.length) {
      return res.status(400).json({ error: 'Some contacts not found or not in organization' });
    }

    // Add contacts to segment (upsert to avoid duplicates)
    const segmentContacts = await Promise.all(
      contacts.map(contact =>
        prisma.segmentContact.upsert({
          where: {
            segmentId_contactId: {
              segmentId: segment.id,
              contactId: contact.id,
            },
          },
          create: {
            segmentId: segment.id,
            contactId: contact.id,
          },
          update: {},
        })
      )
    );

    await auditLog.create(req.user.organizationId, req.user.id, 'Segment', segment.id, { 
      action: 'contacts_added',
      count: segmentContacts.length 
    });

    res.json({ message: `${segmentContacts.length} contacts added to segment` });
  } catch (error) {
    console.error('Error adding contacts to segment:', error);
    res.status(500).json({ error: 'Failed to add contacts to segment' });
  }
});

// DELETE /api/segments/:id/contacts/:contactId - Remove contact from segment
router.delete('/:id/contacts/:contactId', requirePermission('segments:write'), async (req, res) => {
  try {
    const segment = await prisma.segment.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!segment) {
      return res.status(404).json({ error: 'Segment not found' });
    }

    await prisma.segmentContact.delete({
      where: {
        segmentId_contactId: {
          segmentId: segment.id,
          contactId: parseInt(req.params.contactId),
        },
      },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Segment', segment.id, { 
      action: 'contact_removed',
      contactId: req.params.contactId 
    });

    res.json({ message: 'Contact removed from segment' });
  } catch (error) {
    console.error('Error removing contact from segment:', error);
    res.status(500).json({ error: 'Failed to remove contact from segment' });
  }
});

export default router;