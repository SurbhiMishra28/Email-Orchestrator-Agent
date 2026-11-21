import express from 'express';
import { PrismaClient } from '@prisma/client';
import { requirePermission } from '../middleware/rbac.js';
import { auditLog } from '../middleware/auditLog.js';

const prisma = new PrismaClient();
const router = express.Router();

// All routes require authentication (handled by parent middleware)

// GET /api/templates - List templates with filters
router.get('/', requirePermission('templates:read'), async (req, res) => {
  try {
    const { 
      page = 1, 
      limit = 20, 
      search, 
      category, 
      isActive,
      sortBy = 'createdAt',
      sortOrder = 'desc'
    } = req.query;

    const where = {
      organizationId: req.user.organizationId,
    };

    if (search) {
      where.OR = [
        { name: { contains: search, mode: 'insensitive' } },
        { subjectTemplate: { contains: search, mode: 'insensitive' } },
        { bodyTemplate: { contains: search, mode: 'insensitive' } },
      ];
    }

    if (category) where.category = category;
    if (isActive !== undefined) where.isActive = isActive === 'true';

    const [templates, total] = await Promise.all([
      prisma.template.findMany({
        where,
        skip: (page - 1) * limit,
        take: parseInt(limit),
        orderBy: { [sortBy]: sortOrder },
        include: {
          _count: {
            select: { usageLogs: true, campaigns: true },
          },
        },
      }),
      prisma.template.count({ where }),
    ]);

    res.json({
      templates,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    console.error('Error fetching templates:', error);
    res.status(500).json({ error: 'Failed to fetch templates' });
  }
});

// GET /api/templates/:id - Get single template
router.get('/:id', requirePermission('templates:read'), async (req, res) => {
  try {
    const template = await prisma.template.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
      include: {
        usageLogs: {
          take: 10,
          orderBy: { usedAt: 'desc' },
          include: { contact: { select: { id: true, email: true, name: true } } },
        },
        campaigns: {
          select: { id: true, name: true, status: true },
        },
      },
    });

    if (!template) {
      return res.status(404).json({ error: 'Template not found' });
    }

    res.json(template);
  } catch (error) {
    console.error('Error fetching template:', error);
    res.status(500).json({ error: 'Failed to fetch template' });
  }
});

// POST /api/templates - Create template
router.post('/', requirePermission('templates:write'), async (req, res) => {
  try {
    const { name, category, subjectTemplate, bodyTemplate, footerTemplate, variables, tags } = req.body;

    if (!name || !subjectTemplate || !bodyTemplate) {
      return res.status(400).json({ error: 'Name, subjectTemplate, and bodyTemplate are required' });
    }

    const template = await prisma.template.create({
      data: {
        name,
        category: category || 'intro',
        subjectTemplate,
        bodyTemplate,
        footerTemplate: footerTemplate || '',
        variables: variables || {},
        tags: tags || [],
        organizationId: req.user.organizationId,
      },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Template', template.id, { name });

    res.status(201).json(template);
  } catch (error) {
    console.error('Error creating template:', error);
    res.status(500).json({ error: 'Failed to create template' });
  }
});

// PUT /api/templates/:id - Update template
router.put('/:id', requirePermission('templates:write'), async (req, res) => {
  try {
    const { name, category, subjectTemplate, bodyTemplate, footerTemplate, variables, tags, isActive } = req.body;

    const existing = await prisma.template.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!existing) {
      return res.status(404).json({ error: 'Template not found' });
    }

    const template = await prisma.template.update({
      where: { id: parseInt(req.params.id) },
      data: {
        name,
        category,
        subjectTemplate,
        bodyTemplate,
        footerTemplate,
        variables,
        tags,
        isActive,
      },
    });

    await auditLog.update(req.user.organizationId, req.user.id, 'Template', template.id, { name });

    res.json(template);
  } catch (error) {
    console.error('Error updating template:', error);
    res.status(500).json({ error: 'Failed to update template' });
  }
});

// DELETE /api/templates/:id - Delete template
router.delete('/:id', requirePermission('templates:delete'), async (req, res) => {
  try {
    const existing = await prisma.template.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!existing) {
      return res.status(404).json({ error: 'Template not found' });
    }

    await prisma.template.delete({ where: { id: parseInt(req.params.id) } });

    await auditLog.delete(req.user.organizationId, req.user.id, 'Template', req.params.id, { name: existing.name });

    res.json({ message: 'Template deleted successfully' });
  } catch (error) {
    console.error('Error deleting template:', error);
    res.status(500).json({ error: 'Failed to delete template' });
  }
});

// POST /api/templates/:id/approve - Approve template
router.post('/:id/approve', requirePermission('templates:approve'), async (req, res) => {
  try {
    const template = await prisma.template.update({
      where: { id: parseInt(req.params.id) },
      data: { isActive: true },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Template', template.id, { 
      action: 'approved',
      name: template.name 
    });

    res.json(template);
  } catch (error) {
    console.error('Error approving template:', error);
    res.status(500).json({ error: 'Failed to approve template' });
  }
});

// POST /api/templates/:id/duplicate - Duplicate template
router.post('/:id/duplicate', requirePermission('templates:write'), async (req, res) => {
  try {
    const existing = await prisma.template.findFirst({
      where: { id: parseInt(req.params.id), organizationId: req.user.organizationId },
    });

    if (!existing) {
      return res.status(404).json({ error: 'Template not found' });
    }

    const template = await prisma.template.create({
      data: {
        name: `${existing.name} (Copy)`,
        category: existing.category,
        subjectTemplate: existing.subjectTemplate,
        bodyTemplate: existing.bodyTemplate,
        footerTemplate: existing.footerTemplate,
        variables: existing.variables,
        tags: existing.tags,
        organizationId: req.user.organizationId,
        isActive: false,
      },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'Template', template.id, { 
      action: 'duplicated',
      originalId: existing.id 
    });

    res.status(201).json(template);
  } catch (error) {
    console.error('Error duplicating template:', error);
    res.status(500).json({ error: 'Failed to duplicate template' });
  }
});

export default router;