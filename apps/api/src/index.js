import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import dotenv from 'dotenv';
import authRouter from './routers/auth.js';
import contactsRouter from './routers/contacts.js';
import templatesRouter from './routers/templates.js';
import campaignsRouter from './routers/campaigns.js';
import segmentsRouter from './routers/segments.js';
import settingsRouter from './routers/settings.js';
import verificationsRouter from './routers/verifications.js';
import draftsRouter from './routers/drafts.js';
import inboxRouter from './routers/inbox.js';
import automationRouter from './routers/automation.js';
import analyticsRouter from './routers/analytics.js';
import webhooksRouter from './routers/webhooks.js';
import aiRouter from './routers/ai.js';
import foldersRouter from './routers/folders.js';
import listsRouter from './routers/lists.js';
import { authenticate } from './middleware/auth.js';
import { rateLimiters } from './middleware/rateLimit.js';
import { auditLog } from './middleware/auditLog.js';

dotenv.config();
const app = express();

app.use(cors());
app.use(helmet());
app.use(express.json());

// Request logging
app.use((req, res, next) => {
  console.log(`${new Date().toISOString()} ${req.method} ${req.path}`);
  next();
});

// Basic route
app.get('/', (req, res) => {
  res.json({ message: 'API is up and running' });
});

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Mount auth routes with rate limiting
app.use('/api/auth', rateLimiters.auth, authRouter);

// Protected routes - require authentication
app.use('/api', authenticate);

// Apply default rate limiting to all API routes
app.use('/api', rateLimiters.api);

// Mount resource routers
app.use('/api/contacts', contactsRouter);
app.use('/api/templates', templatesRouter);
app.use('/api/campaigns', campaignsRouter);
app.use('/api/segments', segmentsRouter);
app.use('/api/lists', listsRouter);
app.use('/api/folders', foldersRouter);
app.use('/api/settings', settingsRouter);
app.use('/api/verifications', verificationsRouter);
app.use('/api/drafts', draftsRouter);
app.use('/api/inbox', inboxRouter);
app.use('/api/automation', automationRouter);
app.use('/api/analytics', analyticsRouter);
app.use('/api/webhooks', webhooksRouter);
app.use('/api/ai', aiRouter);

export default app;
