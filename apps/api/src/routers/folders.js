import express from 'express';
import { PrismaClient } from '@prisma/client';
import { requirePermission } from '../middleware/rbac.js';
import { auditLog } from '../middleware/auditLog.js';

const prisma = new PrismaClient();
const router = express.Router();

// GET /api/folders - List folders
router.get('/', requirePermission('contacts:read'), async (req, res) => {
  try {
    const folders = await prisma.listFolder.findMany({
      where: {
        organizationId: req.user.organizationId,
        parentFolderId: null, // Only top-level folders
      },
      orderBy: { name: 'asc' },
      include: {
        _count: {
          select: { subfolders: true, lists: true },
        },
        subfolders: {
          where: { organizationId: req.user.organizationId },
          orderBy: { name: 'asc' },
        },
      },
    });

    res.json({ folders });
  } catch (error) {
    console.error('Error fetching folders:', error);
    res.status(500).json({ error: 'Failed to fetch folders' });
  }
});

// GET /api/folders/:id - Get folder with nested subfolders
router.get('/:id', requirePermission('contacts:read'), async (req, res) => {
  try {
    const folder = await prisma.listFolder.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
      include: {
        subfolders: {
          orderBy: { name: 'asc' },
          include: {
            lists: {
              include: {
                _count: {
                  select: { contacts: true },
                },
              },
            },
          },
        },
        lists: {
          include: {
            _count: {
              select: { contacts: true },
            },
          },
        },
      },
    });

    if (!folder) {
      return res.status(404).json({ error: 'Folder not found' });
    }

    res.json({ folder });
  } catch (error) {
    console.error('Error fetching folder:', error);
    res.status(500).json({ error: 'Failed to fetch folder' });
  }
});

// POST /api/folders - Create folder
router.post('/', requirePermission('contacts:write'), async (req, res) => {
  try {
    const { name, parentFolderId, color, icon } = req.body;

    if (!name) {
      return res.status(400).json({ error: 'Name is required' });
    }

    // Check if parent folder exists in the same organization
    if (parentFolderId) {
      const parentFolder = await prisma.listFolder.findFirst({
        where: {
          id: parseInt(parentFolderId),
          organizationId: req.user.organizationId,
        },
      });

      if (!parentFolder) {
        return res.status(400).json({ error: 'Parent folder not found' });
      }
    }

    const folder = await prisma.listFolder.create({
      data: {
        name,
        parentFolderId: parentFolderId ? parseInt(parentFolderId) : undefined,
        organizationId: req.user.organizationId,
        color: color || '#3b82f6',
        icon,
      },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'ListFolder', folder.id, { name });

    res.status(201).json(folder);
  } catch (error) {
    console.error('Error creating folder:', error);
    res.status(500).json({ error: 'Failed to create folder' });
  }
});

// PUT /api/folders/:id - Update folder
router.put('/:id', requirePermission('contacts:write'), async (req, res) => {
  try {
    const { name, color, icon } = req.body;
    const folderPatch = { name, color, icon };

    if (name !== undefined && name === '') {
      return res.status(400).json({ error: 'Name cannot be empty' });
    }

    const folder = await prisma.listFolder.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
    });

    if (!folder) {
      return res.status(404).json({ error: 'Folder not found' });
    }

    const updated = await prisma.listFolder.update({
      where: { id: parseInt(req.params.id) },
      data: folderPatch,
    });

    await auditLog.update(req.user.organizationId, req.user.id, 'ListFolder', updated.id, { name });

    res.json(updated);
  } catch (error) {
    console.error('Error updating folder:', error);
    res.status(500).json({ error: 'Failed to update folder' });
  }
});

// DELETE /api/folders/:id - Delete folder (move lists to root)
router.delete('/:id', requirePermission('contacts:delete'), async (req, res) => {
  try {
    const folder = await prisma.listFolder.findFirst({
      where: {
        id: parseInt(req.params.id),
        organizationId: req.user.organizationId,
      },
    });

    if (!folder) {
      return res.status(404).json({ error: 'Folder not found' });
    }

    // Move all lists in this folder to root (null folderId)
    await prisma.list.updateMany({
      where: { folderId: parseInt(req.params.id) },
      data: { folderId: null },
    });

    // Delete folder
    await prisma.listFolder.delete({
      where: { id: parseInt(req.params.id) },
    });

    await auditLog.delete(req.user.organizationId, req.user.id, 'ListFolder', req.params.id, { name: folder.name });

    res.json({ message: 'Folder deleted successfully' });
  } catch (error) {
    console.error('Error deleting folder:', error);
    res.status(500).json({ error: 'Failed to delete folder' });
  }
});

// GET /api/folders/tree - Get complete folder tree
router.get('/tree', requirePermission('contacts:read'), async (req, res) => {
  try {
    const buildFolderTree = async (parentId = null) => {
      const folders = await prisma.listFolder.findMany({
        where: {
          organizationId: req.user.organizationId,
          parentFolderId: parentId,
        },
        orderBy: { name: 'asc' },
      });

      const tree = await Promise.all(folders.map(async (folder) => {
        const subfolders = await buildFolderTree(folder.id);
        return {
          ...folder,
          children: subfolders,
        };
      }));

      return tree;
    };

    const tree = await buildFolderTree();
    res.json({ tree });
  } catch (error) {
    console.error('Error fetching folder tree:', error);
    res.status(500).json({ error: 'Failed to fetch folder tree' });
  }
});

export default router;