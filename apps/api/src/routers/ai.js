import express from 'express';
import { PrismaClient } from '@prisma/client';
import { requirePermission } from '../middleware/rbac.js';
import { rateLimiters } from '../middleware/rateLimit.js';
import { auditLog } from '../middleware/auditLog.js';
import fetch from 'node-fetch';

const prisma = new PrismaClient();
const router = express.Router();

const AI_ORCHESTRATOR_URL = process.env.AI_ORCHESTRATOR_URL || 'http://localhost:8000';

// POST /api/ai/generate-email - Generate email using AI
router.post('/generate-email', requirePermission('ai:generate'), rateLimiters.aiGenerate, async (req, res) => {
  try {
    const { 
      prompt, 
      tone = 'professional',
      length = 'medium',
      context,
      contact,
      templateId,
      variables,
      model = 'gpt-4'
    } = req.body;

    if (!prompt) {
      return res.status(400).json({ error: 'Prompt is required' });
    }

    // Call AI orchestrator
    const response = await fetch(`${AI_ORCHESTRATOR_URL}/generate/email`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt,
        tone,
        length,
        context,
        contact,
        templateId,
        variables,
        model,
        organizationId: req.user.organizationId,
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'AI generation failed');
    }

    const result = await response.json();

    await auditLog.create(req.user.organizationId, req.user.id, 'AI', null, { 
      action: 'email_generated',
      tone,
      length,
      model 
    });

    res.json(result);
  } catch (error) {
    console.error('Error generating email:', error);
    res.status(500).json({ error: 'Failed to generate email', details: error.message });
  }
});

// POST /api/ai/generate-subject - Generate subject lines
router.post('/generate-subject', requirePermission('ai:generate'), rateLimiters.aiGenerate, async (req, res) => {
  try {
    const { body, tone = 'professional', count = 5, context } = req.body;

    if (!body) {
      return res.status(400).json({ error: 'Email body is required' });
    }

    const response = await fetch(`${AI_ORCHESTRATOR_URL}/generate/subject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body, tone, count, context, organizationId: req.user.organizationId }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'AI generation failed');
    }

    const result = await response.json();

    await auditLog.create(req.user.organizationId, req.user.id, 'AI', null, { 
      action: 'subject_generated',
      tone,
      count 
    });

    res.json(result);
  } catch (error) {
    console.error('Error generating subject:', error);
    res.status(500).json({ error: 'Failed to generate subject lines', details: error.message });
  }
});

// POST /api/ai/optimize-campaign - Optimize campaign with AI
router.post('/optimize-campaign', requirePermission('ai:generate'), rateLimiters.aiGenerate, async (req, res) => {
  try {
    const { campaignId, goals } = req.body;

    if (!campaignId) {
      return res.status(400).json({ error: 'Campaign ID is required' });
    }

    const campaign = await prisma.campaign.findFirst({
      where: { id: parseInt(campaignId), organizationId: req.user.organizationId },
      include: { template: true, targetSegment: true },
    });

    if (!campaign) {
      return res.status(404).json({ error: 'Campaign not found' });
    }

    const response = await fetch(`${AI_ORCHESTRATOR_URL}/optimize/campaign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ campaign, goals, organizationId: req.user.organizationId }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'AI optimization failed');
    }

    const result = await response.json();

    await auditLog.create(req.user.organizationId, req.user.id, 'Campaign', campaignId, { 
      action: 'optimized',
      goals 
    });

    res.json(result);
  } catch (error) {
    console.error('Error optimizing campaign:', error);
    res.status(500).json({ error: 'Failed to optimize campaign', details: error.message });
  }
});

// POST /api/ai/suggest-segments - Suggest segments based on contacts
router.post('/suggest-segments', requirePermission('ai:generate'), rateLimiters.aiGenerate, async (req, res) => {
  try {
    const { contactSample, goals } = req.body;

    const response = await fetch(`${AI_ORCHESTRATOR_URL}/suggest/segments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contactSample, goals, organizationId: req.user.organizationId }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'AI suggestion failed');
    }

    const result = await response.json();

    await auditLog.create(req.user.organizationId, req.user.id, 'AI', null, { 
      action: 'segments_suggested',
      goals 
    });

    res.json(result);
  } catch (error) {
    console.error('Error suggesting segments:', error);
    res.status(500).json({ error: 'Failed to suggest segments', details: error.message });
  }
});

// POST /api/ai/classify-reply - Classify incoming reply
router.post('/classify-reply', requirePermission('ai:generate'), rateLimiters.aiGenerate, async (req, res) => {
  try {
    const { replyText, subject, contact } = req.body;

    if (!replyText) {
      return res.status(400).json({ error: 'Reply text is required' });
    }

    const response = await fetch(`${AI_ORCHESTRATOR_URL}/classify/reply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ replyText, subject, contact, organizationId: req.user.organizationId }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'AI classification failed');
    }

    const result = await response.json();

    res.json(result);
  } catch (error) {
    console.error('Error classifying reply:', error);
    res.status(500).json({ error: 'Failed to classify reply', details: error.message });
  }
});

// POST /api/ai/trigger-agent - Trigger specific AI agent
router.post('/trigger-agent', requirePermission('ai:manage_agents'), async (req, res) => {
  try {
    const { agent, input, config } = req.body;

    if (!agent) {
      return res.status(400).json({ error: 'Agent name is required' });
    }

    const validAgents = [
      'email_writer',
      'subject_generator',
      'campaign_optimizer',
      'segment_analyzer',
      'reply_classifier',
      'deliverability_analyzer',
      'personalization_engine',
    ];

    if (!validAgents.includes(agent)) {
      return res.status(400).json({ error: 'Invalid agent' });
    }

    const response = await fetch(`${AI_ORCHESTRATOR_URL}/agent/${agent}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input, config, organizationId: req.user.organizationId }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Agent execution failed');
    }

    const result = await response.json();

    await auditLog.create(req.user.organizationId, req.user.id, 'AI', null, { 
      action: 'agent_triggered',
      agent 
    });

    res.json(result);
  } catch (error) {
    console.error('Error triggering agent:', error);
    res.status(500).json({ error: 'Failed to trigger agent', details: error.message });
  }
});

// GET /api/ai/agents - List available AI agents
router.get('/agents', requirePermission('ai:manage_agents'), (req, res) => {
  res.json({
    agents: [
      {
        id: 'email_writer',
        name: 'Email Writer',
        description: 'Generates personalized email content',
        capabilities: ['html', 'text', 'personalization', 'multi-tone'],
      },
      {
        id: 'subject_generator',
        name: 'Subject Line Generator',
        description: 'Creates compelling subject lines',
        capabilities: ['a/b_test', 'emoji', 'personalization', 'length_control'],
      },
      {
        id: 'campaign_optimizer',
        name: 'Campaign Optimizer',
        description: 'Optimizes campaigns for better performance',
        capabilities: ['send_time', 'frequency', 'content', 'segmentation'],
      },
      {
        id: 'segment_analyzer',
        name: 'Segment Analyzer',
        description: 'Analyzes contacts and suggests segments',
        capabilities: ['clustering', 'scoring', 'recommendations'],
      },
      {
        id: 'reply_classifier',
        name: 'Reply Classifier',
        description: 'Classifies incoming replies for automation',
        capabilities: ['sentiment', 'intent', 'urgency', 'category'],
      },
      {
        id: 'deliverability_analyzer',
        name: 'Deliverability Analyzer',
        description: 'Monitors and improves email deliverability',
        capabilities: ['spf_dkim_dmarc', 'reputation', 'bounce_analysis', 'warmup'],
      },
      {
        id: 'personalization_engine',
        name: 'Personalization Engine',
        description: 'Creates personalized content at scale',
        capabilities: ['dynamic_content', 'product_recommendations', 'behavioral'],
      },
    ],
  });
});

// GET /api/ai/tones - Get available email tones
router.get('/tones', requirePermission('ai:generate'), (req, res) => {
  res.json({
    tones: [
      { id: 'professional', name: 'Professional', description: 'Formal, business-appropriate tone' },
      { id: 'friendly', name: 'Friendly', description: 'Warm, approachable, conversational' },
      { id: 'casual', name: 'Casual', description: 'Relaxed, informal, like a colleague' },
      { id: 'persuasive', name: 'Persuasive', description: 'Compelling, action-oriented, sales-focused' },
      { id: 'educational', name: 'Educational', description: 'Informative, teaching, value-driven' },
      { id: 'urgent', name: 'Urgent', description: 'Time-sensitive, creates urgency' },
      { id: 'empathetic', name: 'Empathetic', description: 'Understanding, supportive, caring' },
      { id: 'direct', name: 'Direct', description: 'Concise, to-the-point, no fluff' },
    ],
  });
});

// GET /api/ai/health - Check AI orchestrator health
router.get('/health', requirePermission('ai:generate'), async (req, res) => {
  try {
    const response = await fetch(`${AI_ORCHESTRATOR_URL}/health`, { 
      method: 'GET',
      timeout: 5000,
    });

    if (!response.ok) {
      throw new Error('AI orchestrator unhealthy');
    }

    const health = await response.json();
    res.json({ status: 'healthy', orchestrator: health });
  } catch (error) {
    res.status(503).json({ status: 'unhealthy', error: error.message });
  }
});

export default router;