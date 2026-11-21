import express from 'express';
import { PrismaClient } from '@prisma/client';
import { requirePermission } from '../middleware/rbac.js';
import { auditLog } from '../middleware/auditLog.js';

const prisma = new PrismaClient();
const router = express.Router();

// GET /api/lists - List lists with pagination, search, and folder filter
router.get('/', requirePermission('contacts:read'), async (req, res) => {
  try {
    const { page = 1, limit = 20, search, folderId } = req.query;

    const where = {
      organizationId: req.user.organizationId,
    };

    if (search) {
      where.name = { contains: search, mode: 'insensitive' };
    }

    if (folderId && folderId !== 'all') {
      where.folderId = parseInt(folderId);
    }

    const [lists, total] = await Promise.all([
      prisma.list.findMany({
        where,
        skip: (page - 1) * limit,
        take: parseInt(limit),
        orderBy: { createdAt: 'desc' },
        include: {
          _count: {
            select: { contacts: true },
          },
        },
      }),
      prisma.list.count({ where }),
    ]);

    res.json({
      lists,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    console.error('Error fetching lists:', error);
    res.status(500).json({ error: 'Failed to fetch lists' });
  }
});

// GET /api/lists/:id - Get list with contacts
router.get('/:id', requirePermission('contacts:read'), async (req, res) => {
  try {
    const { page = 1, limit = 50 } = req.query;

    const list = await prisma.list.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
      include: {
        folder: true,
        contacts: {
          skip: (page - 1) * limit,
          take: parseInt(limit),
          include: {
            contact: true,
          },
          orderBy: { addedAt: 'desc' },
        },
        _count: {
          select: { contacts: true },
        },
      },
    });

    if (!list) {
      return res.status(404).json({ error: 'List not found' });
    }

    const totalContacts = await prisma.listContact.count({
      where: { listId: list.id },
    });

    res.json({
      ...list,
      contacts: list.contacts.map(lc => lc.contact),
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total: totalContacts,
        totalPages: Math.ceil(totalContacts / limit),
      },
    });
  } catch (error) {
    console.error('Error fetching list:', error);
    res.status(500).json({ error: 'Failed to fetch list' });
  }
});

// POST /api/lists - Create list
router.post('/', requirePermission('contacts:write'), async (req, res) => {
  try {
    const { name, description, folderId, isPublic, color } = req.body;

    if (!name) {
      return res.status(400).json({ error: 'Name is required' });
    }

    // Check if folder exists in the same organization
    if (folderId) {
      const folder = await prisma.listFolder.findFirst({
        where: {
          id: parseInt(folderId),
          organizationId: req.user.organizationId,
        },
      });

      if (!folder) {
        return res.status(400).json({ error: 'Folder not found' });
      }
    }

    const list = await prisma.list.create({
      data: {
        name,
        description,
        folderId: folderId ? parseInt(folderId) : undefined,
        isPublic: isPublic || false,
        color: color || '#3b82f6',
        organizationId: req.user.organizationId,
      },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'List', list.id, { name });

    res.status(201).json(list);
  } catch (error) {
    console.error('Error creating list:', error);
    res.status(500).json({ error: 'Failed to create list' });
  }
});

// PUT /api/lists/:id - Update list
router.put('/:id', requirePermission('contacts:write'), async (req, res) => {
  try {
    const { name, description, folderId, isPublic, color } = req.body;

    if (name !== undefined && name === '') {
      return res.status(400).json({ error: 'Name cannot be empty' });
    }

    // Check if folder exists (if folderId is provided and not null)
    if (folderId !== undefined && folderId !== null && folderId !== '') {
      const folder = await prisma.listFolder.findFirst({
        where: {
          id: parseInt(folderId),
          organizationId: req.user.organizationId,
        },
      });

      if (!folder) {
        return res.status(400).json({ error: 'Folder not found' });
      }
    }

    const list = await prisma.list.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
    });

    if (!list) {
      return res.status(404).json({ error: 'List not found' });
    }

    const updated = await prisma.list.update({
      where: { id: parseInt(req.params.id) },
      data: {
        name,
        description,
        folderId: folderId !== undefined ? (folderId ? parseInt(folderId) : null) : undefined,
        isPublic,
        color,
      },
    });

    await auditLog.update(req.user.organizationId, req.user.id, 'List', updated.id, { name });

    res.json(updated);
  } catch (error) {
    console.error('Error updating list:', error);
    res.status(500).json({ error: 'Failed to update list' });
  }
});

// DELETE /api/lists/:id - Delete list
router.delete('/:id', requirePermission('contacts:delete'), async (req, res) => {
  try {
    const list = await prisma.list.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
    });

    if (!list) {
      return res.status(404).json({ error: 'List not found' });
    }

    await prisma.list.delete({
      where: { id: parseInt(req.params.id) },
    });

    await auditLog.delete(req.user.organizationId, req.user.id, 'List', req.params.id, { name: list.name });

    res.json({ message: 'List deleted successfully' });
  } catch (error) {
    console.error('Error deleting list:', error);
    res.status(500).json({ error: 'Failed to delete list' });
  }
});

// POST /api/lists/:id/contacts - Add contacts to list
router.post('/:id/contacts', requirePermission('contacts:write'), async (req, res) => {
  try {
    const { contactIds } = req.body;

    if (!contactIds || !Array.isArray(contactIds) || contactIds.length === 0) {
      return res.status(400).json({ error: 'contactIds array is required' });
    }

    const list = await prisma.list.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
    });

    if (!list) {
      return res.status(404).json({ error: 'List not found' });
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

    // Add contacts to list (upsert to avoid duplicates)
    await Promise.all(
      contacts.map(contact =>
        prisma.listContact.upsert({
          where: {
            listId_contactId: {
              listId: list.id,
              contactId: contact.id,
            },
          },
          create: {
            listId: list.id,
            contactId: contact.id,
          },
          update: {},
        })
      )
    );

    // Update contact count
    const contactCount = await prisma.listContact.count({
      where: { listId: list.id },
    });

    await prisma.list.update({
      where: { id: list.id },
      data: { contactCount },
    });

    res.json({ message: `${contacts.length} contacts added to list` });
  } catch (error) {
    console.error('Error adding contacts to list:', error);
    res.status(500).json({ error: 'Failed to add contacts to list' });
  }
});

// DELETE /api/lists/:id/contacts - Remove contacts from list
router.delete('/:id/contacts', requirePermission('contacts:write'), async (req, res) => {
  try {
    const { contactIds } = req.body;

    if (!contactIds || !Array.isArray(contactIds) || contactIds.length === 0) {
      return res.status(400).json({ error: 'contactIds array is required' });
    }

    const list = await prisma.list.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
    });

    if (!list) {
      return res.status(404).json({ error: 'List not found' });
    }

    await prisma.listContact.deleteMany({
      where: {
        listId: list.id,
        contactId: { in: contactIds.map(id => parseInt(id)) },
      },
    });

    // Update contact count
    const contactCount = await prisma.listContact.count({
      where: { listId: list.id },
    });

    await prisma.list.update({
      where: { id: list.id },
      data: { contactCount },
    });

    res.json({ message: `${contactIds.length} contacts removed from list` });
  } catch (error) {
    console.error('Error removing contacts from list:', error);
    res.status(500).json({ error: 'Failed to remove contacts from list' });
  }
});

// GET /api/lists/:id/contacts - Get contacts in a list (for bulk operations)
router.get('/:id/contacts', requirePermission('contacts:read'), async (req, res) => {
  try {
    const list = await prisma.list.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
    });

    if (!list) {
      return res.status(404).json({ error: 'List not found' });
    }

    const contacts = await prisma.listContact.findMany({
      where: { listId: list.id },
      include: { contact: true },
    });

    res.json({ contactIds: contacts.map(lc => lc.contact) });
  } catch (error) {
    console.error('Error fetching list contacts:', error);
    res.status(500).json({ error: 'Failed to fetch list contacts' });
  }
});

// POST /api/lists/:id/export - Export list contacts to CSV
router.get('/:id/export', requirePermission('contacts:export'), async (req, res) => {
  try {
    const { page = 1, limit = 50 } = req.query;

    const list = await prisma.list.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
      include: {
        contacts: {
          skip: (page - 1) * limit,
          take: parseInt(limit),
          include: {
            contact: true,
          },
        },
      },
    });

    if (!list) {
      return res.status(404).json({ error: 'List not found' });
    }

    const contacts = list.contacts.map(lc => lc.contact);

    // Generate CSV
    const headers = ['email', 'name', 'company', 'role', 'industry', 'phone', 'linkedin', 'notes', 'tags', 'createdAt'];
    const rows = contacts.map(c => [
      c.email,
      c.name || '',
      c.company || '',
      c.role || '',
      c.industry || '',
      c.phone || '',
      c.linkedin || '',
      c.notes || '',
      (c.tags || []).join(';'),
      c.createdAt.toISOString(),
    ]);

    const csv = [headers.join(','), ...rows.map(r => r.map(v => `"${v.replace(/"/g, '""')}"`).join(','))].join('\n');

    res.setHeader('Content-Type', 'text/csv');
    res.setHeader('Content-Disposition', `attachment; filename="${list.name}-contacts-${Date.now()}.csv"`);
    res.send(csv);
  } catch (error) {
    console.error('Error exporting list:', error);
    res.status(500).json({ error: 'Failed to export list' });
  }
});

export default router;