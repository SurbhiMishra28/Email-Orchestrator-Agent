import express from 'express';
import { PrismaClient } from '@prisma/client';
import crypto from 'crypto';

const prisma = new PrismaClient();
const router = express.Router();

// Email provider webhook endpoints
// These receive events from SendGrid, Mailgun, SES, etc.

// SendGrid webhook
router.post('/sendgrid', express.raw({ type: 'application/json' }), async (req, res) => {
  try {
    // Verify SendGrid signature
    // const signature = req.headers['x-twilio-email-event-webhook-signature'];
    // const timestamp = req.headers['x-twilio-email-event-webhook-timestamp'];
    // Verify using SendGrid's public key

    const events = JSON.parse(req.body.toString());

    for (const event of events) {
      await processEmailEvent('sendgrid', event);
    }

    res.json({ processed: events.length });
  } catch (error) {
    console.error('SendGrid webhook error:', error);
    res.status(500).json({ error: 'Failed to process webhook' });
  }
});

// Mailgun webhook
router.post('/mailgun', async (req, res) => {
  try {
    // Verify Mailgun signature
    // const signature = req.headers['signature'];
    // const token = req.headers['token'];
    // const timestamp = req.headers['timestamp'];
    // Verify using Mailgun API key

    const event = req.body;
    await processEmailEvent('mailgun', event);

    res.json({ processed: 1 });
  } catch (error) {
    console.error('Mailgun webhook error:', error);
    res.status(500).json({ error: 'Failed to process webhook' });
  }
});

// SES webhook (via SNS)
router.post('/ses', async (req, res) => {
  try {
    // Handle SNS subscription confirmation
    if (req.headers['x-amz-sns-message-type'] === 'SubscriptionConfirmation') {
      // TODO: Confirm subscription by visiting SubscribeURL
      return res.json({ message: 'Subscription confirmation received' });
    }

    if (req.headers['x-amz-sns-message-type'] === 'Notification') {
      const message = JSON.parse(req.body.Message);
      await processEmailEvent('ses', message);
    }

    res.json({ processed: 1 });
  } catch (error) {
    console.error('SES webhook error:', error);
    res.status(500).json({ error: 'Failed to process webhook' });
  }
});

// Generic webhook for custom integrations
router.post('/custom', async (req, res) => {
  try {
    const { organizationId, event, data } = req.body;

    // TODO: Validate API key or signature

    await processCustomEvent(organizationId, event, data);

    res.json({ processed: 1 });
  } catch (error) {
    console.error('Custom webhook error:', error);
    res.status(500).json({ error: 'Failed to process webhook' });
  }
});

// Inbound email webhook (for reply handling)
router.post('/inbound', async (req, res) => {
  try {
    // This receives parsed inbound emails from providers
    // Format depends on provider (SendGrid Inbound Parse, Mailgun Routes, etc.)
    
    const { from, to, subject, text, html, headers, organizationId } = req.body;

    // TODO: Parse and create Reply record
    // TODO: Run AI classification
    // TODO: Trigger automation if matched

    res.json({ received: true });
  } catch (error) {
    console.error('Inbound webhook error:', error);
    res.status(500).json({ error: 'Failed to process inbound email' });
  }
});

// Helper function to process email events from providers
async function processEmailEvent(provider, event) {
  try {
    const { email, event: eventType, timestamp, sg_message_id, message_id, ...rest } = event;

    // Map provider event types to standard events
    const eventMap = {
      // SendGrid
      delivered: 'delivered',
      open: 'opened',
      click: 'clicked',
      bounce: 'bounced',
      dropped: 'bounced',
      spam_report: 'complained',
      unsubscribe: 'unsubscribed',
      // Mailgun
      accepted: 'delivered',
      failed: 'bounced',
      complained: 'complained',
      // SES
      delivery: 'delivered',
      bounce: 'bounced',
      complaint: 'complained',
    };

    const standardEvent = eventMap[eventType] || eventType;

    // Find contact and organization
    // This is simplified - in production, use message ID tracking
    const contact = await prisma.contact.findFirst({
      where: { email },
    });

    if (!contact) return;

    // Create event record
    await prisma.event.create({
      data: {
        type: standardEvent,
        payload: { ...rest, provider, originalEvent: eventType, providerMessageId: sg_message_id || message_id },
        contactId: contact.id,
        organizationId: contact.organizationId,
        createdAt: timestamp ? new Date(timestamp * 1000) : new Date(),
      },
    });

    // Update campaign stats if applicable
    if (rest.campaignId) {
      await updateCampaignStats(contact.organizationId, rest.campaignId, standardEvent);
    }

    // Update contact's eligibleToEmail on bounce/complaint
    if (['bounced', 'complained'].includes(standardEvent)) {
      await prisma.contact.update({
        where: { id: contact.id },
        data: { eligibleToEmail: false },
      });

      // Add to suppression list
      // await addToSuppressionList(contact.organizationId, email, standardEvent);
    }
  } catch (error) {
    console.error('Error processing email event:', error);
  }
}

async function processCustomEvent(organizationId, event, data) {
  await prisma.event.create({
    data: {
      type: event,
      payload: data,
      organizationId: parseInt(organizationId),
    },
  });
}

async function updateCampaignStats(organizationId, campaignId, eventType) {
  const updateMap = {
    delivered: { delivered: { increment: 1 } },
    opened: { opened: { increment: 1 } },
    clicked: { clicked: { increment: 1 } },
    replied: { replied: { increment: 1 } },
    bounced: { bounced: { increment: 1 } },
    unsubscribed: { unsubscribed: { increment: 1 } },
  };

  const update = updateMap[eventType];
  if (update) {
    await prisma.campaign.update({
      where: { id: parseInt(campaignId), organizationId },
      data: update,
    });
  }
}

export default router;