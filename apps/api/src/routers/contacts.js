import express from 'express';
import { PrismaClient } from '@prisma/client';
import { requirePermission } from '../middleware/rbac.js';
import { rateLimiters } from '../middleware/rateLimit.js';
import { auditLog } from '../middleware/auditLog.js';
import csv from 'csv-parser';
import { Readable } from 'stream';

const prisma = new PrismaClient();
const router = express.Router();

// GET /api/contacts - List contacts with pagination, filters, sorting
router.get('/', requirePermission('contacts:read'), async (req, res) => {
  try {
    const { 
      page = 1, 
      limit = 50, 
      search, 
      tag, 
      segmentId,
      eligibleToEmail,
      sortBy = 'createdAt',
      sortOrder = 'desc'
    } = req.query;

    const where = {
      organizationId: req.user.organizationId,
    };

    if (search) {
      where.OR = [
        { email: { contains: search, mode: 'insensitive' } },
        { name: { contains: search, mode: 'insensitive' } },
        { company: { contains: search, mode: 'insensitive' } },
      ];
    }

    if (eligibleToEmail !== undefined) {
      where.eligibleToEmail = eligibleToEmail === 'true';
    }

    if (tag) {
      where.tags = { has: tag };
    }

    if (segmentId) {
      const segmentContacts = await prisma.segmentContact.findMany({
        where: { segmentId: parseInt(segmentId) },
        select: { contactId: true },
      });
      where.id = { in: segmentContacts.map(sc => sc.contactId) };
    }

    const [contacts, total] = await Promise.all([
      prisma.contact.findMany({
        where,
        skip: (page - 1) * limit,
        take: parseInt(limit),
        orderBy: { [sortBy]: sortOrder },
        include: {
          _count: { select: { events: true, replies: true, followUps: true } },
        },
      }),
      prisma.contact.count({ where }),
    ]);

    res.json({
      contacts,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    console.error('Error fetching contacts:', error);
    res.status(500).json({ error: 'Failed to fetch contacts' });
  }
});

// GET /api/contacts/stats - Get contact statistics
router.get('/stats', requirePermission('contacts:read'), async (req, res) => {
  try {
    const [total, eligible, byTag, byDomain] = await Promise.all([
      prisma.contact.count({ where: { organizationId: req.user.organizationId } }),
      prisma.contact.count({ where: { organizationId: req.user.organizationId, eligibleToEmail: true } }),
      prisma.contact.groupBy({
        by: ['tags'],
        where: { organizationId: req.user.organizationId },
        _count: true,
      }),
      prisma.$queryRaw`
        SELECT split_part(email, '@', 2) as domain, COUNT(*) as count
        FROM "Contact"
        WHERE "organizationId" = ${req.user.organizationId}
        GROUP BY domain
        ORDER BY count DESC
        LIMIT 20
      `,
    ]);

    // Process tags (they're stored as arrays)
    const tagCounts = {};
    const allContacts = await prisma.contact.findMany({
      where: { organizationId: req.user.organizationId },
      select: { tags: true },
    });
    allContacts.forEach(c => {
      (c.tags || []).forEach(tag => {
        tagCounts[tag] = (tagCounts[tag] || 0) + 1;
      });
    });

    res.json({
      total,
      eligibleToEmail: eligible,
      notEligible: total - eligible,
      topTags: Object.entries(tagCounts).sort((a, b) => b[1] - a[1]).slice(0, 20).map(([tag, count]) => ({ tag, count })),
      topDomains: byDomain,
    });
  } catch (error) {
    console.error('Error fetching contact stats:', error);
    res.status(500).json({ error: 'Failed to fetch contact stats' });
  }
});

// GET /api/contacts/:id - Get single contact
router.get('/:id', requirePermission('contacts:read'), async (req, res) => {
  try {
    const contact = await prisma.contact.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
      include: {
        events: { take: 20, orderBy: { createdAt: 'desc' } },
        verifications: { take: 5, orderBy: { createdAt: 'desc' } },
        drafts: { take: 10, orderBy: { createdAt: 'desc' } },
        segmentContacts: { include: { segment: true } },
        replies: { take: 10, orderBy: { createdAt: 'desc' } },
        followUps: { take: 10, orderBy: { createdAt: 'desc' } },
      },
    });

    if (!contact) {
      return res.status(404).json({ error: 'Contact not found' });
    }

    res.json(contact);
  } catch (error) {
    console.error('Error fetching contact:', error);
    res.status(500).json({ error: 'Failed to fetch contact' });
  }
});

// POST /api/contacts - Create contact
router.post('/', requirePermission('contacts:write'), async (req, res) => {
  try {
    const { email, name, company, role, industry, phone, linkedin, notes, customFields, tags } = req.body;

    if (!email) {
      return res.status(400).json({ error: 'Email is required' });
    }

    // Check if contact already exists in organization
    const existing = await prisma.contact.findUnique({
      where: { organizationId_email: { organizationId: req.user.organizationId, email } },
    });

    if (existing) {
      return res.status(409).json({ error: 'Contact with this email already exists', contact: existing });
    }

    const contact = await prisma.contact.create({
      data: {
        email,
        name,
        company,
        role,
        industry,
        phone,
        linkedin,
        notes,
        customFields: customFields || {},
        tags: tags || [],
        organizationId: req.user.organizationId,
      },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Contact', contact.id, { email, name });

    res.status(201).json(contact);
  } catch (error) {
    console.error('Error creating contact:', error);
    res.status(500).json({ error: 'Failed to create contact' });
  }
});

// PUT /api/contacts/:id - Update contact
router.put('/:id', requirePermission('contacts:write'), async (req, res) => {
  try {
    const { email, name, company, role, industry, phone, linkedin, notes, customFields, tags, eligibleToEmail } = req.body;

    const existing = await prisma.contact.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!existing) {
      return res.status(404).json({ error: 'Contact not found' });
    }

    // Check email uniqueness if changing
    if (email && email !== existing.email) {
      const duplicate = await prisma.contact.findUnique({
        where: { organizationId_email: { organizationId: req.user.organizationId, email } },
      });
      if (duplicate) {
        return res.status(409).json({ error: 'Contact with this email already exists' });
      }
    }

    const contact = await prisma.contact.update({
      where: { id: parseInt(req.params.id) },
      data: {
        email,
        name,
        company,
        role,
        industry,
        phone,
        linkedin,
        notes,
        customFields,
        tags,
        eligibleToEmail,
      },
    });

    await auditLog.update(req.user.organizationId, req.user.id, 'Contact', contact.id, { email, name });

    res.json(contact);
  } catch (error) {
    console.error('Error updating contact:', error);
    res.status(500).json({ error: 'Failed to update contact' });
  }
});

// DELETE /api/contacts/:id - Delete contact
router.delete('/:id', requirePermission('contacts:delete'), async (req, res) => {
  try {
    const existing = await prisma.contact.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!existing) {
      return res.status(404).json({ error: 'Contact not found' });
    }

    await prisma.contact.delete({ where: { id: parseInt(req.params.id) } });

    await auditLog.delete(req.user.organizationId, req.user.id, 'Contact', req.params.id, { email: existing.email });

    res.json({ message: 'Contact deleted successfully' });
  } catch (error) {
    console.error('Error deleting contact:', error);
    res.status(500).json({ error: 'Failed to delete contact' });
  }
});

// POST /api/contacts/bulk - Bulk create/update contacts
router.post('/bulk', requirePermission('contacts:write'), async (req, res) => {
  try {
    const { contacts, upsert = false } = req.body;

    if (!contacts || !Array.isArray(contacts) || contacts.length === 0) {
      return res.status(400).json({ error: 'Contacts array is required' });
    }

    if (contacts.length > 1000) {
      return res.status(400).json({ error: 'Maximum 1000 contacts per request' });
    }

    const results = { created: 0, updated: 0, errors: [] };

    for (let i = 0; i < contacts.length; i++) {
      const contactData = contacts[i];
      if (!contactData.email) {
        results.errors.push({ index: i, error: 'Email is required' });
        continue;
      }

      try {
        const existing = await prisma.contact.findUnique({
          where: { organizationId_email: { organizationId: req.user.organizationId, email: contactData.email } },
        });

        if (existing) {
          if (upsert) {
            await prisma.contact.update({
              where: { id: existing.id },
              data: { ...contactData, organizationId: req.user.organizationId },
            });
            results.updated++;
          } else {
            results.errors.push({ index: i, email: contactData.email, error: 'Contact already exists' });
          }
        } else {
          await prisma.contact.create({
            data: { ...contactData, organizationId: req.user.organizationId },
          });
          results.created++;
        }
      } catch (error) {
        results.errors.push({ index: i, email: contactData.email, error: error.message });
      }
    }

    await auditLog.create(req.user.organizationId, req.user.id, 'Contact', null, { 
      action: 'bulk_created',
      created: results.created,
      updated: results.updated 
    });

    res.json(results);
  } catch (error) {
    console.error('Error bulk creating contacts:', error);
    res.status(500).json({ error: 'Failed to bulk create contacts' });
  }
});

// POST /api/contacts/import - Import contacts from CSV
router.post('/import', requirePermission('contacts:import'), rateLimiters.import, async (req, res) => {
  try {
    // This endpoint expects multipart/form-data with a 'file' field
    // For simplicity, we'll accept JSON with csvContent
    const { csvContent, skipHeader = true } = req.body;

    if (!csvContent) {
      return res.status(400).json({ error: 'CSV content is required' });
    }

    const results = { created: 0, updated: 0, errors: [] };
    const lines = csvContent.trim().split('\n');
    const startIndex = skipHeader ? 1 : 0;

    for (let i = startIndex; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;

      // Simple CSV parsing (in production, use a proper CSV parser)
      const values = line.split(',').map(v => v.trim().replace(/^"|"$/g, ''));
      if (values.length < 1) continue;

      const email = values[0];
      if (!email || !email.includes('@')) {
        results.errors.push({ line: i + 1, error: 'Invalid email' });
        continue;
      }

      const contactData = {
        email,
        name: values[1] || null,
        company: values[2] || null,
        role: values[3] || null,
        industry: values[4] || null,
        phone: values[5] || null,
        linkedin: values[6] || null,
        notes: values[7] || null,
      };

      try {
        const existing = await prisma.contact.findUnique({
          where: { organizationId_email: { organizationId: req.user.organizationId, email } },
        });

        if (existing) {
          await prisma.contact.update({
            where: { id: existing.id },
            data: contactData,
          });
          results.updated++;
        } else {
          await prisma.contact.create({
            data: { ...contactData, organizationId: req.user.organizationId },
          });
          results.created++;
        }
      } catch (error) {
        results.errors.push({ line: i + 1, email, error: error.message });
      }
    }

    await auditLog.create(req.user.organizationId, req.user.id, 'Contact', null, { 
      action: 'imported',
      created: results.created,
      updated: results.updated 
    });

    res.json(results);
  } catch (error) {
    console.error('Error importing contacts:', error);
    res.status(500).json({ error: 'Failed to import contacts' });
  }
});

// GET /api/contacts/export - Export contacts to CSV
router.get('/export', requirePermission('contacts:export'), rateLimiters.export, async (req, res) => {
  try {
    const { search, tag, segmentId, eligibleToEmail } = req.query;

    const where = { organizationId: req.user.organizationId };
    if (search) where.OR = [{ email: { contains: search, mode: 'insensitive' } }, { name: { contains: search, mode: 'insensitive' } }];
    if (eligibleToEmail !== undefined) where.eligibleToEmail = eligibleToEmail === 'true';
    if (tag) where.tags = { has: tag };
    if (segmentId) {
      const segmentContacts = await prisma.segmentContact.findMany({
        where: { segmentId: parseInt(segmentId) },
        select: { contactId: true },
      });
      where.id = { in: segmentContacts.map(sc => sc.contactId) };
    }

    const contacts = await prisma.contact.findMany({
      where,
      orderBy: { createdAt: 'desc' },
    });

    // Generate CSV
    const headers = ['email', 'name', 'company', 'role', 'industry', 'phone', 'linkedin', 'notes', 'eligibleToEmail', 'tags', 'createdAt'];
    const rows = contacts.map(c => [
      c.email,
      c.name || '',
      c.company || '',
      c.role || '',
      c.industry || '',
      c.phone || '',
      c.linkedin || '',
      c.notes || '',
      c.eligibleToEmail ? 'true' : 'false',
      (c.tags || []).join(';'),
      c.createdAt.toISOString(),
    ]);

    const csv = [headers.join(','), ...rows.map(r => r.map(v => `"${v.replace(/"/g, '""')}"`).join(','))].join('\n');

    await auditLog.create(req.user.organizationId, req.user.id, 'Contact', null, { 
      action: 'exported',
      count: contacts.length 
    });

    res.setHeader('Content-Type', 'text/csv');
    res.setHeader('Content-Disposition', `attachment; filename="contacts-${Date.now()}.csv"`);
    res.send(csv);
  } catch (error) {
    console.error('Error exporting contacts:', error);
    res.status(500).json({ error: 'Failed to export contacts' });
  }
});

// DELETE /api/contacts/bulk - Bulk delete contacts
router.delete('/bulk', requirePermission('contacts:delete'), async (req, res) => {
  try {
    const { contactIds } = req.body;

    if (!contactIds || !Array.isArray(contactIds) || contactIds.length === 0) {
      return res.status(400).json({ error: 'contactIds array is required' });
    }

    const contacts = await prisma.contact.findMany({
      where: { id: { in: contactIds.map(id => parseInt(id)) }, organizationId: req.user.organizationId },
    });

    if (contacts.length === 0) {
      return res.status(404).json({ error: 'No contacts found' });
    }

    await prisma.contact.deleteMany({
      where: { id: { in: contacts.map(c => c.id) } },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Contact', null, { 
      action: 'bulk_deleted',
      count: contacts.length,
      emails: contacts.map(c => c.email) 
    });

    res.json({ message: `${contacts.length} contacts deleted` });
  } catch (error) {
    console.error('Error bulk deleting contacts:', error);
    res.status(500).json({ error: 'Failed to delete contacts' });
  }
});

// POST /api/contacts/:id/tags - Add tag to contact
router.post('/:id/tags', requirePermission('contacts:write'), async (req, res) => {
  try {
    const { tag } = req.body;

    if (!tag) {
      return res.status(400).json({ error: 'Tag is required' });
    }

    const contact = await prisma.contact.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!contact) {
      return res.status(404).json({ error: 'Contact not found' });
    }

    // Add tag to contact's tags array
    const tags = [...new Set([...(contact.tags || []), tag])];
    const updated = await prisma.contact.update({
      where: { id: contact.id },
      data: { tags },
    });

    // Also create/update Tag record
    await prisma.tag.upsert({
      where: { organizationId_name: { organizationId: req.user.organizationId, name: tag } },
      create: { name: tag, organizationId: req.user.organizationId },
      update: {},
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Contact', contact.id, { 
      action: 'tag_added',
      tag 
    });

    res.json(updated);
  } catch (error) {
    console.error('Error adding tag:', error);
    res.status(500).json({ error: 'Failed to add tag' });
  }
});

// DELETE /api/contacts/:id/tags/:tag - Remove tag from contact
router.delete('/:id/tags/:tag', requirePermission('contacts:write'), async (req, res) => {
  try {
    const contact = await prisma.contact.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!contact) {
      return res.status(404).json({ error: 'Contact not found' });
    }

    const tags = (contact.tags || []).filter(t => t !== req.params.tag);
    const updated = await prisma.contact.update({
      where: { id: contact.id },
      data: { tags },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Contact', contact.id, { 
      action: 'tag_removed',
      tag: req.params.tag 
    });

    res.json(updated);
  } catch (error) {
    console.error('Error removing tag:', error);
    res.status(500).json({ error: 'Failed to remove tag' });
  }
});

// GET /api/contacts/tags - Get all tags
router.get('/tags', requirePermission('contacts:read'), async (req, res) => {
  try {
    const tags = await prisma.tag.findMany({
      where: { organizationId: req.user.organizationId },
      orderBy: { name: 'asc' },
    });

    res.json({ tags });
  } catch (error) {
    console.error('Error fetching tags:', error);
    res.status(500).json({ error: 'Failed to fetch tags' });
  }
});

export default router;