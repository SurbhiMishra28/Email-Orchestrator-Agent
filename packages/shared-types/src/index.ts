import { z } from 'zod';

// --- Enums ---

export const UserRole = z.enum(['OWNER', 'ADMIN', 'MANAGER', 'MEMBER', 'VIEWER']);
export type UserRole = z.infer<typeof UserRole>;

export const OrganizationStatus = z.enum(['active', 'inactive', 'suspended', 'trial']);
export type OrganizationStatus = z.infer<typeof OrganizationStatus>;

export const OrganizationPlan = z.enum(['free', 'starter', 'growth', 'enterprise']);
export type OrganizationPlan = z.infer<typeof OrganizationPlan>;

export const CampaignStatus = z.enum(['draft', 'pending_approval', 'approved', 'scheduled', 'sending', 'sent', 'paused', 'cancelled', 'rejected']);
export type CampaignStatus = z.infer<typeof CampaignStatus>;

export const CampaignType = z.enum(['regular', 'ab_test', 'automated', 'follow_up']);
export type CampaignType = z.infer<typeof CampaignType>;

export const ContactStatus = z.enum(['subscribed', 'unsubscribed', 'bounced', 'complained', 'pending']);
export type ContactStatus = z.infer<typeof ContactStatus>;

export const EmailVerificationStatus = z.enum(['valid', 'invalid', 'risky', 'unknown', 'catch_all', 'disposable']);
export type EmailVerificationStatus = z.infer<typeof EmailVerificationStatus>;

export const TemplateCategory = z.enum(['intro', 'follow_up', 'newsletter', 'promotional', 'transactional', 'custom']);
export type TemplateCategory = z.infer<typeof TemplateCategory>;

export const EmailTone = z.enum(['professional', 'friendly', 'casual', 'persuasive', 'educational', 'urgent', 'empathetic', 'direct']);
export type EmailTone = z.infer<typeof EmailTone>;

export const EventType = z.enum([
  'email_sent', 'email_delivered', 'email_opened', 'email_clicked', 
  'email_replied', 'email_bounced', 'email_unsubscribed', 'email_complained',
  'contact_created', 'contact_updated', 'contact_deleted',
  'campaign_created', 'campaign_sent', 'campaign_completed',
  'automation_triggered', 'automation_completed',
  'reply_received', 'reply_classified'
]);
export type EventType = z.infer<typeof EventType>;

export const AiAgentType = z.enum([
  'email_writer', 'subject_generator', 'campaign_optimizer', 
  'segment_analyzer', 'reply_classifier', 'deliverability_analyzer', 'personalization_engine'
]);
export type AiAgentType = z.infer<typeof AiAgentType>;

export const AutomationTriggerType = z.enum([
  'contact_added', 'contact_updated', 'tag_added', 'tag_removed',
  'email_opened', 'email_clicked', 'email_replied', 'form_submitted',
  'schedule', 'webhook', 'segment_entered', 'segment_exited'
]);
export type AutomationTriggerType = z.infer<typeof AutomationTriggerType>;

export const AutomationActionType = z.enum([
  'send_email', 'add_tag', 'remove_tag', 'update_contact',
  'add_to_segment', 'remove_from_segment', 'create_task',
  'notify_slack', 'webhook', 'delay', 'condition',
  'ai_generate_email', 'ai_classify_reply'
]);
export type AutomationActionType = z.infer<typeof AutomationActionType>;

export const WebhookEvent = z.enum([
  'contact.created', 'contact.updated', 'contact.deleted',
  'campaign.sent', 'campaign.completed',
  'email.delivered', 'email.opened', 'email.clicked', 'email.replied', 'email.bounced', 'email.unsubscribed',
  'reply.received', 'reply.classified',
  'automation.triggered', 'automation.completed'
]);
export type WebhookEvent = z.infer<typeof WebhookEvent>;

export const SmtpProvider = z.enum(['custom', 'sendgrid', 'mailgun', 'ses', 'postmark', 'sparkpost']);
export type SmtpProvider = z.infer<typeof SmtpProvider>;

// --- Base Schemas ---

export const PaginationSchema = z.object({
  page: z.number().int().positive().default(1),
  limit: z.number().int().positive().max(100).default(20),
  sortBy: z.string().optional(),
  sortOrder: z.enum(['asc', 'desc']).default('desc'),
});

export const DateRangeSchema = z.object({
  startDate: z.string().datetime().optional(),
  endDate: z.string().datetime().optional(),
});

// --- User & Organization ---

export const UserSchema = z.object({
  id: z.number(),
  email: z.string().email(),
  name: z.string().nullable(),
  image: z.string().nullable(),
  emailVerified: z.date().nullable(),
  createdAt: z.date(),
  updatedAt: z.date(),
  organizationId: z.number().nullable(),
  role: UserRole,
});

export const OrganizationSchema = z.object({
  id: z.number(),
  name: z.string(),
  slug: z.string(),
  description: z.string().nullable(),
  plan: OrganizationPlan,
  status: OrganizationStatus,
  createdAt: z.date(),
  updatedAt: z.date(),
});

export const OrganizationRoleSchema = z.object({
  id: z.number(),
  organizationId: z.number(),
  userId: z.number(),
  role: UserRole,
  joinedAt: z.date(),
});

// --- Contact ---

export const ContactSchema = z.object({
  id: z.number(),
  email: z.string().email(),
  name: z.string().nullable(),
  company: z.string().nullable(),
  role: z.string().nullable(),
  industry: z.string().nullable(),
  phone: z.string().nullable(),
  linkedin: z.string().nullable(),
  notes: z.string().nullable(),
  eligibleToEmail: z.boolean(),
  tags: z.array(z.string()),
  customFields: z.record(z.unknown()),
  organizationId: z.number(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export const ContactCreateSchema = z.object({
  email: z.string().email(),
  name: z.string().optional(),
  company: z.string().optional(),
  role: z.string().optional(),
  industry: z.string().optional(),
  phone: z.string().optional(),
  linkedin: z.string().optional(),
  notes: z.string().optional(),
  customFields: z.record(z.unknown()).optional(),
  tags: z.array(z.string()).optional(),
});

export const ContactUpdateSchema = ContactCreateSchema.partial();

// --- Template ---

export const TemplateSchema = z.object({
  id: z.number(),
  name: z.string(),
  category: TemplateCategory,
  subjectTemplate: z.string(),
  bodyTemplate: z.string(),
  footerTemplate: z.string(),
  variables: z.record(z.unknown()),
  tags: z.array(z.string()),
  isActive: z.boolean(),
  organizationId: z.number(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export const TemplateCreateSchema = z.object({
  name: z.string().min(1),
  category: TemplateCategory.default('custom'),
  subjectTemplate: z.string().min(1),
  bodyTemplate: z.string().min(1),
  footerTemplate: z.string().optional(),
  variables: z.record(z.unknown()).optional(),
  tags: z.array(z.string()).optional(),
});

export const TemplateUpdateSchema = TemplateCreateSchema.partial();

// --- Campaign ---

export const CampaignSchema = z.object({
  id: z.number(),
  name: z.string(),
  description: z.string().nullable(),
  type: CampaignType,
  status: CampaignStatus,
  templateId: z.number().nullable(),
  targetSegmentId: z.number().nullable(),
  abTestConfig: z.record(z.unknown()).nullable(),
  scheduledAt: z.date().nullable(),
  sentAt: z.date().nullable(),
  delivered: z.number(),
  opened: z.number(),
  clicked: z.number(),
  replied: z.number(),
  bounced: z.number(),
  unsubscribed: z.number(),
  organizationId: z.number(),
  createdById: z.number().nullable(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export const CampaignCreateSchema = z.object({
  name: z.string().min(1),
  description: z.string().optional(),
  type: CampaignType.default('regular'),
  templateId: z.number().optional(),
  targetSegmentId: z.number().optional(),
  abTestConfig: z.record(z.unknown()).optional(),
  scheduledAt: z.string().datetime().optional(),
});

export const CampaignUpdateSchema = CampaignCreateSchema.partial().extend({
  status: CampaignStatus.optional(),
});

// --- Segment ---

export const SegmentSchema = z.object({
  id: z.number(),
  name: z.string(),
  description: z.string().nullable(),
  query: z.record(z.unknown()),
  organizationId: z.number(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export const SegmentCreateSchema = z.object({
  name: z.string().min(1),
  description: z.string().optional(),
  query: z.record(z.unknown()),
});

export const SegmentUpdateSchema = SegmentCreateSchema.partial();

// --- Custom Lists ---

export const ListFolderSchema = z.object({
  id: z.number(),
  name: z.string(),
  organizationId: z.number(),
  parentFolderId: z.number().nullable(),
  color: z.string(),
  icon: z.string().nullable(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export const ListFolderCreateSchema = z.object({
  name: z.string().min(1),
  parentFolderId: z.number().optional(),
  color: z.string().optional(),
  icon: z.string().optional(),
});

export const ListFolderUpdateSchema = ListFolderCreateSchema.partial();

export const ListSchema = z.object({
  id: z.number(),
  name: z.string(),
  description: z.string().nullable(),
  organizationId: z.number(),
  folderId: z.number().nullable(),
  isPublic: z.boolean(),
  color: z.string(),
  contactCount: z.number(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export const ListCreateSchema = z.object({
  name: z.string().min(1),
  description: z.string().optional(),
  folderId: z.number().optional(),
  isPublic: z.boolean().optional(),
  color: z.string().optional(),
});

export const ListUpdateSchema = ListCreateSchema.partial();

export const ListContactSchema = z.object({
  id: z.number(),
  listId: z.number(),
  contactId: z.number(),
  addedAt: z.date(),
});

// --- Email Verification ---

export const EmailVerificationSchema = z.object({
  id: z.number(),
  email: z.string().email(),
  contactId: z.number().nullable(),
  organizationId: z.number(),
  status: EmailVerificationStatus,
  smtpCheck: z.string(),
  mxCheck: z.string(),
  catchAll: z.boolean(),
  disposable: z.boolean(),
  domain: z.string().nullable(),
  lastChecked: z.date().nullable(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

// --- Draft ---

export const DraftSchema = z.object({
  id: z.number(),
  subject: z.string(),
  body: z.string(),
  status: z.enum(['draft', 'approved', 'sending', 'sent', 'failed']),
  contactId: z.number().nullable(),
  variables: z.record(z.unknown()),
  priority: z.enum(['low', 'normal', 'high']),
  organizationId: z.number(),
  createdAt: z.date(),
  sentAt: z.date().nullable(),
  errorMessage: z.string().nullable(),
  attempts: z.number(),
  lastAttemptAt: z.date().nullable(),
});

export const DraftCreateSchema = z.object({
  subject: z.string().min(1),
  body: z.string().min(1),
  contactId: z.number().optional(),
  variables: z.record(z.unknown()).optional(),
  priority: z.enum(['low', 'normal', 'high']).default('normal'),
});

// --- Event ---

export const EventSchema = z.object({
  id: z.number(),
  type: EventType,
  payload: z.record(z.unknown()),
  contactId: z.number().nullable(),
  organizationId: z.number(),
  userId: z.number().nullable(),
  createdAt: z.date(),
});

// --- Settings ---

export const SettingsSchema = z.object({
  id: z.number(),
  organizationId: z.number(),
  goal: z.string(),
  businessName: z.string(),
  businessOffer: z.string(),
  dailyCap: z.number(),
  domainCap: z.number(),
  AUTO_APPROVE: z.boolean(),
  AUTOPILOT: z.boolean(),
  footerText: z.string(),
  senderName: z.string(),
  senderRole: z.string(),
  companyWebsite: z.string(),
  calendlyUrl: z.string(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export const SmtpConfigSchema = z.object({
  host: z.string(),
  port: z.number().int().positive(),
  user: z.string(),
  password: z.string(),
  fromEmail: z.string().email(),
  fromName: z.string(),
  tls: z.boolean().default(true),
  provider: SmtpProvider.default('custom'),
});

export const SenderDomainSchema = z.object({
  id: z.number(),
  domain: z.string(),
  status: z.enum(['pending', 'verified', 'failed']),
  spfValid: z.boolean(),
  dkimValid: z.boolean(),
  dmarcValid: z.boolean(),
  organizationId: z.number(),
  createdAt: z.date(),
});

export const WebhookSchema = z.object({
  id: z.number(),
  url: z.string().url(),
  events: z.array(WebhookEvent),
  secret: z.string(),
  active: z.boolean(),
  organizationId: z.number(),
  createdAt: z.date(),
});

export const ApiKeySchema = z.object({
  id: z.number(),
  key: z.string(),
  name: z.string(),
  permissions: z.array(z.string()),
  lastUsed: z.date().nullable(),
  expiresAt: z.date().nullable(),
  organizationId: z.number(),
  createdById: z.number(),
  createdAt: z.date(),
});

// --- Inbox ---

export const InboxConfigSchema = z.object({
  id: z.number(),
  organizationId: z.number(),
  imapHost: z.string(),
  imapPort: z.number(),
  imapUser: z.string(),
  imapPassword: z.string(),
  imapTls: z.boolean(),
  lastSync: z.date().nullable(),
  status: z.enum(['connected', 'disconnected', 'syncing', 'error']),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export const ReplySchema = z.object({
  id: z.number(),
  email: z.string().email(),
  subject: z.string(),
  bodyPreview: z.string(),
  sentiment: z.enum(['positive', 'neutral', 'negative']),
  classification: z.enum(['interested', 'not_interested', 'unsubscribe', 'question', 'out_of_office', 'bounce', 'other']),
  contactId: z.number().nullable(),
  organizationId: z.number(),
  createdAt: z.date(),
  autoReplyStatus: z.enum(['pending', 'sent', 'failed']),
  autoReplyMessage: z.string().nullable(),
});

// --- Automation ---

export const AutomationSchema = z.object({
  id: z.number(),
  name: z.string(),
  description: z.string().nullable(),
  trigger: z.object({
    type: AutomationTriggerType,
    config: z.record(z.unknown()),
  }),
  steps: z.array(z.object({
    id: z.string(),
    type: AutomationActionType,
    config: z.record(z.unknown()),
    conditions: z.array(z.record(z.unknown())).optional(),
  })),
  status: z.enum(['draft', 'active', 'paused', 'completed']),
  organizationId: z.number(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

// --- AI ---

export const AiGenerateEmailRequestSchema = z.object({
  prompt: z.string().min(1),
  tone: EmailTone.default('professional'),
  length: z.enum(['short', 'medium', 'long']).default('medium'),
  context: z.string().optional(),
  contact: ContactSchema.optional(),
  templateId: z.number().optional(),
  variables: z.record(z.unknown()).optional(),
  model: z.string().default('gpt-4'),
});

export const AiGenerateSubjectRequestSchema = z.object({
  body: z.string().min(1),
  tone: EmailTone.default('professional'),
  count: z.number().int().positive().max(10).default(5),
  context: z.string().optional(),
});

export const AiOptimizeCampaignRequestSchema = z.object({
  campaign: CampaignSchema,
  goals: z.array(z.enum(['open_rate', 'click_rate', 'reply_rate', 'deliverability'])).optional(),
});

export const AiClassifyReplyRequestSchema = z.object({
  replyText: z.string().min(1),
  subject: z.string().optional(),
  contact: ContactSchema.optional(),
});

export const AiAgentResponseSchema = z.object({
  success: z.boolean(),
  data: z.unknown(),
  error: z.string().optional(),
  usage: z.object({
    promptTokens: z.number(),
    completionTokens: z.number(),
    totalTokens: z.number(),
  }).optional(),
});

// --- Analytics ---

export const AnalyticsOverviewSchema = z.object({
  totals: z.object({
    sent: z.number(),
    delivered: z.number(),
    opened: z.number(),
    clicked: z.number(),
    replied: z.number(),
    bounced: z.number(),
    unsubscribed: z.number(),
  }),
  rates: z.object({
    deliveryRate: z.string(),
    openRate: z.string(),
    clickRate: z.string(),
    replyRate: z.string(),
    bounceRate: z.string(),
    unsubscribeRate: z.string(),
  }),
  campaignsByStatus: z.record(z.number()),
  contacts: z.object({
    total: z.number(),
    newThisMonth: z.number(),
  }),
});

export const CampaignAnalyticsSchema = z.object({
  id: z.number(),
  name: z.string(),
  status: CampaignStatus,
  sentAt: z.date().nullable(),
  delivered: z.number(),
  opened: z.number(),
  clicked: z.number(),
  replied: z.number(),
  bounced: z.number(),
  unsubscribed: z.number(),
  deliveryRate: z.string(),
  openRate: z.string(),
  clickRate: z.string(),
  replyRate: z.string(),
});

// --- API Response ---

export const ApiResponseSchema = <T extends z.ZodTypeAny>(dataSchema: T) =>
  z.object({
    success: z.boolean(),
    data: dataSchema.optional(),
    error: z.string().optional(),
    message: z.string().optional(),
  });

export const PaginatedResponseSchema = <T extends z.ZodTypeAny>(itemSchema: T) =>
  z.object({
    success: z.boolean(),
    data: z.array(itemSchema),
    pagination: z.object({
      page: z.number(),
      limit: z.number(),
      total: z.number(),
      totalPages: z.number(),
    }),
    error: z.string().optional(),
  });

// --- Type Exports ---

export type User = z.infer<typeof UserSchema>;
export type Organization = z.infer<typeof OrganizationSchema>;
export type OrganizationRole = z.infer<typeof OrganizationRoleSchema>;
export type Contact = z.infer<typeof ContactSchema>;
export type ContactCreate = z.infer<typeof ContactCreateSchema>;
export type ContactUpdate = z.infer<typeof ContactUpdateSchema>;
export type Template = z.infer<typeof TemplateSchema>;
export type TemplateCreate = z.infer<typeof TemplateCreateSchema>;
export type TemplateUpdate = z.infer<typeof TemplateUpdateSchema>;
export type Campaign = z.infer<typeof CampaignSchema>;
export type CampaignCreate = z.infer<typeof CampaignCreateSchema>;
export type CampaignUpdate = z.infer<typeof CampaignUpdateSchema>;
export type Segment = z.infer<typeof SegmentSchema>;
export type SegmentCreate = z.infer<typeof SegmentCreateSchema>;
export type SegmentUpdate = z.infer<typeof SegmentUpdateSchema>;

// --- Custom Lists ---

export type ListFolder = z.infer<typeof ListFolderSchema>;
export type ListFolderCreate = z.infer<typeof ListFolderCreateSchema>;
export type ListFolderUpdate = z.infer<typeof ListFolderUpdateSchema>;
export type List = z.infer<typeof ListSchema>;
export type ListCreate = z.infer<typeof ListCreateSchema>;
export type ListUpdate = z.infer<typeof ListUpdateSchema>;
export type ListContact = z.infer<typeof ListContactSchema>;

// --- Email Verification ---

export type EmailVerification = z.infer<typeof EmailVerificationSchema>;
export type Draft = z.infer<typeof DraftSchema>;
export type DraftCreate = z.infer<typeof DraftCreateSchema>;
export type Event = z.infer<typeof EventSchema>;
export type Settings = z.infer<typeof SettingsSchema>;
export type SmtpConfig = z.infer<typeof SmtpConfigSchema>;
export type SenderDomain = z.infer<typeof SenderDomainSchema>;
export type Webhook = z.infer<typeof WebhookSchema>;
export type ApiKey = z.infer<typeof ApiKeySchema>;
export type InboxConfig = z.infer<typeof InboxConfigSchema>;
export type Reply = z.infer<typeof ReplySchema>;
export type Automation = z.infer<typeof AutomationSchema>;
export type AiGenerateEmailRequest = z.infer<typeof AiGenerateEmailRequestSchema>;
export type AiGenerateSubjectRequest = z.infer<typeof AiGenerateSubjectRequestSchema>;
export type AiOptimizeCampaignRequest = z.infer<typeof AiOptimizeCampaignRequestSchema>;
export type AiClassifyReplyRequest = z.infer<typeof AiClassifyReplyRequestSchema>;
export type AiAgentResponse = z.infer<typeof AiAgentResponseSchema>;
export type AnalyticsOverview = z.infer<typeof AnalyticsOverviewSchema>;
export type CampaignAnalytics = z.infer<typeof CampaignAnalyticsSchema>;