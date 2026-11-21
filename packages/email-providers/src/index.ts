import nodemailer from 'nodemailer';
import sgMail from '@sendgrid/mail';
import Mailgun, { InputFormData } from 'mailgun.js';
import { SESClient, SendEmailCommand, SendRawEmailCommand } from '@aws-sdk/client-ses';
import { SmtpConfig, SmtpProvider } from '@email-orchestrator/shared-types';

export interface EmailProvider {
  sendEmail(params: SendEmailParams): Promise<SendEmailResult>;
  sendBatchEmail(params: BatchEmailParams): Promise<BatchEmailResult>;
  verifyConnection(): Promise<boolean>;
}

export interface SendEmailParams {
  to: string | string[];
  from: string;
  fromName?: string;
  subject: string;
  text?: string;
  html?: string;
  replyTo?: string;
  headers?: Record<string, string>;
  attachments?: EmailAttachment[];
  tags?: string[];
  metadata?: Record<string, string>;
}

export interface BatchEmailParams {
  messages: SendEmailParams[];
}

export interface SendEmailResult {
  success: boolean;
  messageId?: string;
  error?: string;
  provider: string;
}

export interface BatchEmailResult {
  success: boolean;
  results: SendEmailResult[];
  error?: string;
  provider?: string;
}

export interface EmailAttachment {
  filename: string;
  content: Buffer | string;
  contentType?: string;
  cid?: string;
}

// --- SMTP Provider (Nodemailer) ---

export class SmtpEmailProvider implements EmailProvider {
  private transporter: nodemailer.Transporter;

  constructor(private config: SmtpConfig) {
    this.transporter = nodemailer.createTransport({
      host: config.host,
      port: config.port,
      secure: config.port === 465,
      auth: {
        user: config.user,
        pass: config.password,
      },
      tls: config.tls ? { rejectUnauthorized: true } : undefined,
    });
  }

  async sendEmail(params: SendEmailParams): Promise<SendEmailResult> {
    try {
      const info = await this.transporter.sendMail({
        from: `${params.fromName || ''} <${params.from}>`.trim(),
        to: Array.isArray(params.to) ? params.to.join(', ') : params.to,
        subject: params.subject,
        text: params.text,
        html: params.html,
        replyTo: params.replyTo,
        headers: params.headers,
        attachments: params.attachments?.map(a => ({
          filename: a.filename,
          content: a.content,
          contentType: a.contentType,
          cid: a.cid,
        })),
      });

      return {
        success: true,
        messageId: info.messageId,
        provider: 'smtp',
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
        provider: 'smtp',
      };
    }
  }

  async sendBatchEmail(params: BatchEmailParams): Promise<BatchEmailResult> {
    const results = await Promise.all(
      params.messages.map(msg => this.sendEmail(msg))
    );

    return {
      success: results.every(r => r.success),
      results,
      provider: 'smtp',
    };
  }

  async verifyConnection(): Promise<boolean> {
    try {
      await this.transporter.verify();
      return true;
    } catch {
      return false;
    }
  }
}

// --- SendGrid Provider ---

export class SendGridEmailProvider implements EmailProvider {
  constructor(private apiKey: string) {
    sgMail.setApiKey(apiKey);
  }

  async sendEmail(params: SendEmailParams): Promise<SendEmailResult> {
    try {
      const msg = {
        to: params.to,
        from: { email: params.from, name: params.fromName },
        subject: params.subject,
        text: params.text,
        html: params.html,
        replyTo: params.replyTo,
        headers: params.headers,
        attachments: params.attachments?.map(a => ({
          filename: a.filename,
          content: a.content instanceof Buffer ? a.content.toString('base64') : a.content,
          type: a.contentType,
          disposition: a.cid ? 'inline' : 'attachment',
          contentId: a.cid,
        })),
        categories: params.tags,
        customArgs: params.metadata,
      } as unknown as sgMail.MailDataRequired;

      const response = await sgMail.send(msg);
      const firstResponse = Array.isArray(response)
        ? (response[0] as { headers?: Record<string, string> })
        : (response as unknown as { headers?: Record<string, string> });
      return {
        success: true,
        messageId: firstResponse?.headers?.['x-message-id'],
        provider: 'sendgrid',
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
        provider: 'sendgrid',
      };
    }
  }

  async sendBatchEmail(params: BatchEmailParams): Promise<BatchEmailResult> {
    try {
      const messages = params.messages.map(msg => ({
        to: msg.to,
        from: { email: msg.from, name: msg.fromName },
        subject: msg.subject,
        text: msg.text,
        html: msg.html,
        replyTo: msg.replyTo,
        headers: msg.headers,
        attachments: msg.attachments?.map(a => ({
          filename: a.filename,
          content: a.content instanceof Buffer ? a.content.toString('base64') : a.content,
          type: a.contentType,
          disposition: a.cid ? 'inline' : 'attachment',
          contentId: a.cid,
        })),
        categories: msg.tags,
        customArgs: msg.metadata,
      })) as unknown as sgMail.MailDataRequired[];

      const responses = await sgMail.send(messages);
      const list = (Array.isArray(responses) ? responses : [responses]) as unknown as {
        headers?: Record<string, string>;
      }[];
      const results = list.map(response => ({
        success: true,
        messageId: response?.headers?.['x-message-id'],
        provider: 'sendgrid',
      }));

      return { success: true, results, provider: 'sendgrid' };
    } catch (error) {
      return {
        success: false,
        results: [],
        error: error instanceof Error ? error.message : 'Unknown error',
        provider: 'sendgrid',
      };
    }
  }

  async verifyConnection(): Promise<boolean> {
    try {
      // SendGrid doesn't have a direct verify endpoint, but we can try a test send
      await sgMail.send({
        to: 'test@example.com',
        from: 'test@example.com',
        subject: 'Test',
        text: 'Test',
        mailSettings: { sandboxMode: { enable: true } },
      });
      return true;
    } catch {
      return false;
    }
  }
}

// --- Mailgun Provider ---

export class MailgunEmailProvider implements EmailProvider {
  private client: ReturnType<Mailgun['client']>;

  constructor(private apiKey: string, private domain: string) {
    const mailgun = new Mailgun(globalThis.FormData as unknown as InputFormData);
    this.client = mailgun.client({ username: 'api', key: apiKey });
  }

  async sendEmail(params: SendEmailParams): Promise<SendEmailResult> {
    try {
      const data = {
        from: `${params.fromName || ''} <${params.from}>`.trim(),
        to: Array.isArray(params.to) ? params.to : [params.to],
        subject: params.subject,
        text: params.text,
        html: params.html,
        'h:Reply-To': params.replyTo,
        'o:tag': params.tags,
        'o:tracking': true,
        'o:tracking-clicks': true,
        'o:tracking-opens': true,
      } as unknown as Parameters<typeof this.client.messages.create>[1];

      const response = await this.client.messages.create(this.domain, data);
      return {
        success: true,
        messageId: response.id,
        provider: 'mailgun',
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
        provider: 'mailgun',
      };
    }
  }

  async sendBatchEmail(params: BatchEmailParams): Promise<BatchEmailResult> {
    const results = await Promise.all(
      params.messages.map(msg => this.sendEmail(msg))
    );

    return {
      success: results.every(r => r.success),
      results,
      provider: 'mailgun',
    };
  }

  async verifyConnection(): Promise<boolean> {
    try {
      await this.client.domains.get(this.domain);
      return true;
    } catch {
      return false;
    }
  }
}

// --- AWS SES Provider ---

export class SesEmailProvider implements EmailProvider {
  private client: SESClient;

  constructor(
    private region: string,
    private accessKeyId: string,
    private secretAccessKey: string
  ) {
    this.client = new SESClient({
      region: this.region,
      credentials: {
        accessKeyId: this.accessKeyId,
        secretAccessKey: this.secretAccessKey,
      },
    });
  }

  async sendEmail(params: SendEmailParams): Promise<SendEmailResult> {
    try {
      const command = new SendEmailCommand({
        Source: `${params.fromName || ''} <${params.from}>`.trim(),
        Destination: {
          ToAddresses: Array.isArray(params.to) ? params.to : [params.to],
        },
        Message: {
          Subject: { Data: params.subject, Charset: 'UTF-8' },
          Body: {
            Text: params.text ? { Data: params.text, Charset: 'UTF-8' } : undefined,
            Html: params.html ? { Data: params.html, Charset: 'UTF-8' } : undefined,
          },
        },
        ReplyToAddresses: params.replyTo ? [params.replyTo] : undefined,
        Tags: params.tags?.map(tag => ({ Name: 'tag', Value: tag })),
        ConfigurationSetName: params.metadata?.configurationSet,
      });

      const response = await this.client.send(command);
      return {
        success: true,
        messageId: response.MessageId,
        provider: 'ses',
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
        provider: 'ses',
      };
    }
  }

  async sendBatchEmail(params: BatchEmailParams): Promise<BatchEmailResult> {
    // SES doesn't have native batch send, send sequentially
    const results = await Promise.all(
      params.messages.map(msg => this.sendEmail(msg))
    );

    return {
      success: results.every(r => r.success),
      results,
      provider: 'ses',
    };
  }

  async verifyConnection(): Promise<boolean> {
    try {
      // Try to get send quota as a connection test
      await this.client.send(new SendEmailCommand({
        Source: 'test@example.com',
        Destination: { ToAddresses: ['test@example.com'] },
        Message: {
          Subject: { Data: 'Test', Charset: 'UTF-8' },
          Body: { Text: { Data: 'Test', Charset: 'UTF-8' } },
        },
      }));
      return true;
    } catch {
      return false;
    }
  }
}

// --- Factory ---

export function createEmailProvider(config: SmtpConfig): EmailProvider {
  switch (config.provider) {
    case 'sendgrid':
      return new SendGridEmailProvider(config.password); // password field used for API key
    case 'mailgun':
      return new MailgunEmailProvider(config.password, config.host); // host used for domain
    case 'ses':
      return new SesEmailProvider(
        config.host, // host used for region
        config.user, // user used for access key
        config.password // password used for secret key
      );
    case 'custom':
    default:
      return new SmtpEmailProvider(config);
  }
}

// --- Email Template Renderer ---

export function renderTemplate(template: string, variables: Record<string, unknown>): string {
  return template.replace(/\{\{(\w+)\}\}/g, (match, key) => {
    const value = variables[key];
    return value !== undefined ? String(value) : match;
  });
}

export function renderEmailSubject(subjectTemplate: string, variables: Record<string, unknown>): string {
  return renderTemplate(subjectTemplate, variables);
}

export function renderEmailBody(bodyTemplate: string, variables: Record<string, unknown>): { html: string; text: string } {
  const html = renderTemplate(bodyTemplate, variables);
  // Simple HTML to text conversion
  const text = html
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&/g, '&')
    .replace(/</g, '<')
    .replace(/>/g, '>')
    .replace(/"/g, '"')
    .trim();

  return { html, text };
}