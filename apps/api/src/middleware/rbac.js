import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

const ROLE_HIERARCHY = {
  OWNER: 5,
  ADMIN: 4,
  MANAGER: 3,
  MEMBER: 2,
  VIEWER: 1,
};

const PERMISSIONS = {
  // Organization
  'org:read': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER', 'VIEWER'],
  'org:write': ['OWNER', 'ADMIN'],
  'org:delete': ['OWNER'],
  'org:manage_members': ['OWNER', 'ADMIN'],
  'org:manage_settings': ['OWNER', 'ADMIN'],
  'org:manage_billing': ['OWNER', 'ADMIN'],

  // Contacts
  'contacts:read': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER', 'VIEWER'],
  'contacts:write': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER'],
  'contacts:delete': ['OWNER', 'ADMIN', 'MANAGER'],
  'contacts:import': ['OWNER', 'ADMIN', 'MANAGER'],
  'contacts:export': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER'],
  'contacts:verify': ['OWNER', 'ADMIN', 'MANAGER'],

  // Templates
  'templates:read': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER', 'VIEWER'],
  'templates:write': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER'],
  'templates:delete': ['OWNER', 'ADMIN', 'MANAGER'],
  'templates:approve': ['OWNER', 'ADMIN'],

  // Campaigns
  'campaigns:read': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER', 'VIEWER'],
  'campaigns:write': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER'],
  'campaigns:delete': ['OWNER', 'ADMIN', 'MANAGER'],
  'campaigns:send': ['OWNER', 'ADMIN', 'MANAGER'],
  'campaigns:approve': ['OWNER', 'ADMIN'],
  'campaigns:ab_test': ['OWNER', 'ADMIN', 'MANAGER'],

  // Segments
  'segments:read': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER', 'VIEWER'],
  'segments:write': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER'],
  'segments:delete': ['OWNER', 'ADMIN', 'MANAGER'],

  // Lists
  'lists:read': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER', 'VIEWER'],
  'lists:write': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER'],
  'lists:delete': ['OWNER', 'ADMIN', 'MANAGER'],

  // Folders
  'folders:read': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER', 'VIEWER'],
  'folders:write': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER'],
  'folders:delete': ['OWNER', 'ADMIN', 'MANAGER'],

  // Analytics
  'analytics:read': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER', 'VIEWER'],
  'analytics:export': ['OWNER', 'ADMIN', 'MANAGER'],

  // Inbox/Replies
  'inbox:read': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER', 'VIEWER'],
  'inbox:write': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER'],
  'inbox:manage': ['OWNER', 'ADMIN'],

  // Automation
  'automation:read': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER', 'VIEWER'],
  'automation:write': ['OWNER', 'ADMIN', 'MANAGER'],
  'automation:execute': ['OWNER', 'ADMIN', 'MANAGER'],

  // Settings
  'settings:read': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER', 'VIEWER'],
  'settings:write': ['OWNER', 'ADMIN'],
  'settings:manage_smtp': ['OWNER', 'ADMIN'],
  'settings:manage_webhooks': ['OWNER', 'ADMIN'],
  'settings:manage_api_keys': ['OWNER', 'ADMIN'],
  'settings:view_audit_logs': ['OWNER', 'ADMIN'],

  // AI
  'ai:generate': ['OWNER', 'ADMIN', 'MANAGER', 'MEMBER'],
  'ai:manage_agents': ['OWNER', 'ADMIN'],
};

export function hasPermission(userRole, permission) {
  const allowedRoles = PERMISSIONS[permission];
  if (!allowedRoles) return false;
  return allowedRoles.includes(userRole);
}

export function requirePermission(permission) {
  return async (req, res, next) => {
    try {
      const userId = req.user?.id;
      const organizationId = req.user?.organizationId;

      if (!userId || !organizationId) {
        return res.status(401).json({ error: 'Unauthorized' });
      }

      const membership = await prisma.organizationRole.findUnique({
        where: {
          organizationId_userId: {
            organizationId,
            userId,
          },
        },
      });

      if (!membership) {
        return res.status(403).json({ error: 'No access to this organization' });
      }

      const userRole = membership.role;
      if (!hasPermission(userRole, permission)) {
        return res.status(403).json({ 
          error: 'Insufficient permissions',
          required: permission,
          currentRole: userRole,
        });
      }

      req.userRole = userRole;
      next();
    } catch (error) {
      console.error('RBAC error:', error);
      res.status(500).json({ error: 'Internal server error' });
    }
  };
}

export function requireRole(...allowedRoles) {
  return async (req, res, next) => {
    try {
      const userId = req.user?.id;
      const organizationId = req.user?.organizationId;

      if (!userId || !organizationId) {
        return res.status(401).json({ error: 'Unauthorized' });
      }

      const membership = await prisma.organizationRole.findUnique({
        where: {
          organizationId_userId: {
            organizationId,
            userId,
          },
        },
      });

      if (!membership || !allowedRoles.includes(membership.role)) {
        return res.status(403).json({ error: 'Insufficient role' });
      }

      req.userRole = membership.role;
      next();
    } catch (error) {
      console.error('Role check error:', error);
      res.status(500).json({ error: 'Internal server error' });
    }
  };
}

export async function getUserRole(userId, organizationId) {
  const membership = await prisma.organizationRole.findUnique({
    where: {
      organizationId_userId: {
        organizationId,
        userId,
      },
    },
  });
  return membership?.role || null;
}

export { ROLE_HIERARCHY, PERMISSIONS };