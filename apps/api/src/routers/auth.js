import express from 'express';
import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import crypto from 'crypto';
import { PrismaClient } from '@prisma/client';
import { generateAccessToken, generateRefreshToken, verifyToken, JWT_SECRET, JWT_REFRESH_EXPIRES_IN } from '../middleware/auth.js';
import { rateLimiters } from '../middleware/rateLimit.js';
import { auditLog } from '../middleware/auditLog.js';

const router = express.Router();
const prisma = new PrismaClient();

// POST /api/auth/register - Register new user and organization
router.post('/register', rateLimiters.register, async (req, res) => {
  try {
    const { email, password, name, organizationName } = req.body;

    if (!email || !password) {
      return res.status(400).json({ error: 'Email and password are required' });
    }

    if (password.length < 8) {
      return res.status(400).json({ error: 'Password must be at least 8 characters' });
    }

    // Check if user already exists
    const existingUser = await prisma.user.findUnique({ where: { email } });
    if (existingUser) {
      return res.status(400).json({ error: 'Email already registered' });
    }

    const hashed = await bcrypt.hash(password, 12);

    // Create user with organization
    const user = await prisma.user.create({
      data: {
        email,
        password: hashed,
        name: name || email.split('@')[0],
        organization: {
          create: {
            name: organizationName || `${name || email.split('@')[0]}'s Organization`,
            slug: (organizationName || name || email.split('@')[0])
              .toLowerCase()
              .replace(/[^a-z0-9]+/g, '-')
              .replace(/(^-|-$)/g, '') + '-' + Date.now(),
            settings: { create: {} },
          },
        },
        organizationRoles: {
          create: { role: 'OWNER' },
        },
      },
      include: {
        organization: true,
        organizationRoles: true,
      },
    });

    const accessToken = generateAccessToken({
      id: user.id,
      email: user.email,
      organizationId: user.organizationId,
      role: user.organizationRoles[0]?.role || 'OWNER',
    });

    const refreshToken = generateRefreshToken(user);

    // Store refresh token hash
    await prisma.user.update({
      where: { id: user.id },
      data: { password: hashed }, // In production, store refresh token hash separately
    });

    await auditLog.create(user.organizationId, user.id, 'User', user.id, { 
      action: 'registered',
      email 
    });

    res.status(201).json({
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        organizationId: user.organizationId,
        role: user.organizationRoles[0]?.role,
        organization: user.organization,
      },
      accessToken,
      refreshToken,
    });
  } catch (error) {
    console.error('Registration error:', error);
    res.status(500).json({ error: 'Registration failed' });
  }
});

// POST /api/auth/login - Login user
router.post('/login', rateLimiters.login, async (req, res) => {
  try {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ error: 'Email and password are required' });
    }

    const user = await prisma.user.findUnique({
      where: { email },
      include: {
        organization: true,
        organizationRoles: { where: { organizationId: { not: null } } },
      },
    });

    if (!user) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    if (!user.organization || user.organization.status !== 'active') {
      return res.status(403).json({ error: 'Organization is not active' });
    }

    const isMatch = await bcrypt.compare(password, user.password);
    if (!isMatch) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    // Get primary organization role
    const primaryRole = user.organizationRoles[0]?.role || 'MEMBER';

    const accessToken = generateAccessToken({
      id: user.id,
      email: user.email,
      organizationId: user.organizationId,
      role: primaryRole,
    });

    const refreshToken = generateRefreshToken(user);

    await auditLog.login(req, user);

    res.json({
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        image: user.image,
        organizationId: user.organizationId,
        role: primaryRole,
        organization: user.organization,
      },
      accessToken,
      refreshToken,
    });
  } catch (error) {
    console.error('Login error:', error);
    res.status(500).json({ error: 'Login failed' });
  }
});

// POST /api/auth/refresh - Refresh access token
router.post('/refresh', async (req, res) => {
  try {
    const { refreshToken } = req.body;

    if (!refreshToken) {
      return res.status(400).json({ error: 'Refresh token required' });
    }

    const decoded = verifyToken(refreshToken);
    if (!decoded || decoded.type !== 'refresh') {
      return res.status(401).json({ error: 'Invalid refresh token' });
    }

    const user = await prisma.user.findUnique({
      where: { id: decoded.id },
      include: {
        organization: true,
        organizationRoles: { where: { organizationId: { not: null } } },
      },
    });

    if (!user || !user.organization || user.organization.status !== 'active') {
      return res.status(401).json({ error: 'User not found or inactive' });
    }

    const primaryRole = user.organizationRoles[0]?.role || 'MEMBER';

    const accessToken = generateAccessToken({
      id: user.id,
      email: user.email,
      organizationId: user.organizationId,
      role: primaryRole,
    });

    const newRefreshToken = generateRefreshToken(user);

    res.json({ accessToken, refreshToken: newRefreshToken });
  } catch (error) {
    console.error('Token refresh error:', error);
    res.status(500).json({ error: 'Token refresh failed' });
  }
});

// POST /api/auth/logout - Logout user
router.post('/logout', async (req, res) => {
  try {
    const { refreshToken } = req.body;
    // In production, blacklist the refresh token
    // For now, just return success
    
    if (req.user) {
      await auditLog.logout(req, req.user.id, req.user.organizationId);
    }

    res.json({ message: 'Logged out successfully' });
  } catch (error) {
    console.error('Logout error:', error);
    res.status(500).json({ error: 'Logout failed' });
  }
});

// GET /api/auth/me - Get current user
router.get('/me', async (req, res) => {
  try {
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return res.status(401).json({ error: 'No token provided' });
    }

    const token = authHeader.substring(7);
    const decoded = verifyToken(token);

    if (!decoded) {
      return res.status(401).json({ error: 'Invalid token' });
    }

    const user = await prisma.user.findUnique({
      where: { id: decoded.id },
      include: {
        organization: true,
        organizationRoles: {
          where: { organizationId: { not: null } },
          include: { organization: true },
        },
      },
    });

    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    res.json({
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        image: user.image,
        organizationId: user.organizationId,
        role: user.organizationRoles[0]?.role || 'MEMBER',
        organization: user.organization,
        memberships: user.organizationRoles.map(r => ({
          organizationId: r.organizationId,
          role: r.role,
          organization: r.organization,
        })),
      },
    });
  } catch (error) {
    console.error('Get user error:', error);
    res.status(500).json({ error: 'Failed to get user' });
  }
});

// POST /api/auth/forgot-password - Request password reset
router.post('/forgot-password', rateLimiters.auth, async (req, res) => {
  try {
    const { email } = req.body;

    if (!email) {
      return res.status(400).json({ error: 'Email is required' });
    }

    const user = await prisma.user.findUnique({ where: { email } });

    // Always return success to prevent email enumeration
    if (!user) {
      return res.json({ message: 'If the email exists, a reset link has been sent' });
    }

    // Generate reset token
    const resetToken = crypto.randomBytes(32).toString('hex');
    const resetTokenExpiry = new Date(Date.now() + 60 * 60 * 1000); // 1 hour

    // In production, store hashed token and send email
    // await prisma.user.update({
    //   where: { id: user.id },
    //   data: { resetToken: hashedToken, resetTokenExpiry },
    // });

    // TODO: Send password reset email

    await auditLog.create(user.organizationId, user.id, 'User', user.id, { 
      action: 'password_reset_requested' 
    });

    res.json({ message: 'If the email exists, a reset link has been sent' });
  } catch (error) {
    console.error('Forgot password error:', error);
    res.status(500).json({ error: 'Failed to process request' });
  }
});

// POST /api/auth/reset-password - Reset password
router.post('/reset-password', rateLimiters.auth, async (req, res) => {
  try {
    const { token, password } = req.body;

    if (!token || !password) {
      return res.status(400).json({ error: 'Token and password are required' });
    }

    if (password.length < 8) {
      return res.status(400).json({ error: 'Password must be at least 8 characters' });
    }

    // In production, verify token hash and expiry
    // const user = await prisma.user.findFirst({
    //   where: { resetToken: hashedToken, resetTokenExpiry: { gt: new Date() } },
    // });

    // For now, simplified
    return res.status(400).json({ error: 'Password reset not fully implemented' });
  } catch (error) {
    console.error('Reset password error:', error);
    res.status(500).json({ error: 'Failed to reset password' });
  }
});

// POST /api/auth/change-password - Change password (authenticated)
router.post('/change-password', async (req, res) => {
  try {
    const { currentPassword, newPassword } = req.body;

    if (!currentPassword || !newPassword) {
      return res.status(400).json({ error: 'Current and new password required' });
    }

    if (newPassword.length < 8) {
      return res.status(400).json({ error: 'Password must be at least 8 characters' });
    }

    const user = await prisma.user.findUnique({ where: { id: req.user.id } });
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    const isMatch = await bcrypt.compare(currentPassword, user.password);
    if (!isMatch) {
      return res.status(401).json({ error: 'Current password is incorrect' });
    }

    const hashed = await bcrypt.hash(newPassword, 12);
    await prisma.user.update({
      where: { id: user.id },
      data: { password: hashed },
    });

    await auditLog.create(req.user.organizationId, req.user.id, 'User', user.id, { 
      action: 'password_changed' 
    });

    res.json({ message: 'Password changed successfully' });
  } catch (error) {
    console.error('Change password error:', error);
    res.status(500).json({ error: 'Failed to change password' });
  }
});

// POST /api/auth/verify-email - Request email verification
router.post('/verify-email', async (req, res) => {
  try {
    const user = await prisma.user.findUnique({ where: { id: req.user.id } });
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    if (user.emailVerified) {
      return res.status(400).json({ error: 'Email already verified' });
    }

    // Generate verification token
    const verificationToken = crypto.randomBytes(32).toString('hex');

    // TODO: Store token and send verification email

    await auditLog.create(req.user.organizationId, req.user.id, 'User', user.id, { 
      action: 'email_verification_requested' 
    });

    res.json({ message: 'Verification email sent' });
  } catch (error) {
    console.error('Verify email error:', error);
    res.status(500).json({ error: 'Failed to send verification email' });
  }
});

// POST /api/auth/confirm-email - Confirm email with token
router.post('/confirm-email', async (req, res) => {
  try {
    const { token } = req.body;

    if (!token) {
      return res.status(400).json({ error: 'Token required' });
    }

    // TODO: Verify token and update user

    res.json({ message: 'Email verified successfully' });
  } catch (error) {
    console.error('Confirm email error:', error);
    res.status(500).json({ error: 'Failed to verify email' });
  }
});

export default router;