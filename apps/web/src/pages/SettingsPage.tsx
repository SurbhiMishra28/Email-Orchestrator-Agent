import React, { useState } from 'react';
import { Tabs, Card, CardHeader, CardTitle, CardContent, Button, Input, Badge, Select, Table } from '@email-orchestrator/ui-components';
import { Mail, Shield, Users, Key, Globe, Webhook, Activity, Save } from 'lucide-react';

const settingsTabs = [
  { value: 'general', label: 'General', icon: Mail },
  { value: 'smtp', label: 'SMTP', icon: Send },
  { value: 'domains', label: 'Domains', icon: Globe },
  { value: 'webhooks', label: 'Webhooks', icon: Webhook },
  { value: 'api-keys', label: 'API Keys', icon: Key },
  { value: 'team', label: 'Team', icon: Users },
  { value: 'audit', label: 'Audit Logs', icon: Activity },
];

function Send({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
    </svg>
  );
}

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState('general');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-gray-600">Manage your organization settings</p>
      </div>

      <Tabs tabs={settingsTabs} activeTab={activeTab} onChange={setActiveTab} />

      {activeTab === 'general' && <GeneralSettings />}
      {activeTab === 'smtp' && <SmtpSettings />}
      {activeTab === 'domains' && <DomainSettings />}
      {activeTab === 'webhooks' && <WebhookSettings />}
      {activeTab === 'api-keys' && <ApiKeySettings />}
      {activeTab === 'team' && <TeamSettings />}
      {activeTab === 'audit' && <AuditLogSettings />}
    </div>
  );
}

function GeneralSettings() {
  const [formData, setFormData] = useState({
    businessName: '',
    businessOffer: '',
    goal: 'Book intro calls with sales leaders',
    dailyCap: 50,
    domainCap: 3,
    autoApprove: false,
    autopilot: false,
    footerText: '',
    senderName: '',
    senderRole: '',
    companyWebsite: '',
    calendlyUrl: '',
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>General Settings</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6 max-w-2xl">
        <div className="grid gap-4 md:grid-cols-2">
          <Input label="Business Name" value={formData.businessName} onChange={e => setFormData(prev => ({ ...prev, businessName: e.target.value }))} />
          <Input label="Business Offer" value={formData.businessOffer} onChange={e => setFormData(prev => ({ ...prev, businessOffer: e.target.value }))} />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Goal</label>
          <textarea
            className="w-full min-h-[100px] rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            value={formData.goal}
            onChange={e => setFormData(prev => ({ ...prev, goal: e.target.value }))}
          />
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <Input label="Daily Send Cap" type="number" value={formData.dailyCap} onChange={e => setFormData(prev => ({ ...prev, dailyCap: parseInt(e.target.value) }))} />
          <Input label="Domain Cap" type="number" value={formData.domainCap} onChange={e => setFormData(prev => ({ ...prev, domainCap: parseInt(e.target.value) }))} />
          <Input label="Company Website" value={formData.companyWebsite} onChange={e => setFormData(prev => ({ ...prev, companyWebsite: e.target.value }))} />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Input label="Sender Name" value={formData.senderName} onChange={e => setFormData(prev => ({ ...prev, senderName: e.target.value }))} />
          <Input label="Sender Role" value={formData.senderRole} onChange={e => setFormData(prev => ({ ...prev, senderRole: e.target.value }))} />
        </div>
        <Input label="Footer Text" value={formData.footerText} onChange={e => setFormData(prev => ({ ...prev, footerText: e.target.value }))} />
        <Input label="Calendly URL" value={formData.calendlyUrl} onChange={e => setFormData(prev => ({ ...prev, calendlyUrl: e.target.value }))} />
        
        <div className="space-y-4">
          <label className="flex items-center gap-3">
            <input type="checkbox" checked={formData.autoApprove} onChange={e => setFormData(prev => ({ ...prev, autoApprove: e.target.checked }))} className="rounded border-gray-300" />
            <span className="text-sm">Auto-approve campaigns</span>
          </label>
          <label className="flex items-center gap-3">
            <input type="checkbox" checked={formData.autopilot} onChange={e => setFormData(prev => ({ ...prev, autopilot: e.target.checked }))} className="rounded border-gray-300" />
            <span className="text-sm">Autopilot mode</span>
          </label>
        </div>

        <Button><Save className="w-4 h-4 mr-2" />Save Settings</Button>
      </CardContent>
    </Card>
  );
}

function SmtpSettings() {
  const [formData, setFormData] = useState({
    provider: 'custom',
    host: '',
    port: 587,
    user: '',
    password: '',
    fromEmail: '',
    fromName: '',
    tls: true,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>SMTP Configuration</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6 max-w-2xl">
        <div className="grid gap-4 md:grid-cols-2">
          <Select
            label="Provider"
            value={formData.provider}
            onChange={e => setFormData(prev => ({ ...prev, provider: e.target.value }))}
            options={[
              { value: 'custom', label: 'Custom SMTP' },
              { value: 'sendgrid', label: 'SendGrid' },
              { value: 'mailgun', label: 'Mailgun' },
              { value: 'ses', label: 'Amazon SES' },
            ]}
          />
          <Input label="From Email" type="email" value={formData.fromEmail} onChange={e => setFormData(prev => ({ ...prev, fromEmail: e.target.value }))} />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Input label="Host" value={formData.host} onChange={e => setFormData(prev => ({ ...prev, host: e.target.value }))} />
          <Input label="Port" type="number" value={formData.port} onChange={e => setFormData(prev => ({ ...prev, port: parseInt(e.target.value) }))} />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Input label="Username / API Key" value={formData.user} onChange={e => setFormData(prev => ({ ...prev, user: e.target.value }))} />
          <Input label="Password / Secret" type="password" value={formData.password} onChange={e => setFormData(prev => ({ ...prev, password: e.target.value }))} />
        </div>
        <Input label="From Name" value={formData.fromName} onChange={e => setFormData(prev => ({ ...prev, fromName: e.target.value }))} />
        
        <label className="flex items-center gap-3">
          <input type="checkbox" checked={formData.tls} onChange={e => setFormData(prev => ({ ...prev, tls: e.target.checked }))} className="rounded border-gray-300" />
          <span className="text-sm">Use TLS</span>
        </label>

        <div className="flex gap-2">
          <Button variant="outline">Test Connection</Button>
          <Button><Save className="w-4 h-4 mr-2" />Save Configuration</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function DomainSettings() {
  const [domains] = useState([
    { domain: 'example.com', status: 'verified', spf: true, dkim: true, dmarc: true },
    { domain: 'mail.example.com', status: 'pending', spf: false, dkim: false, dmarc: false },
  ]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <CardTitle className="text-lg">Sender Domains</CardTitle>
        <Button>Add Domain</Button>
      </div>
      <Card>
        <CardContent className="p-0">
          <Table
            columns={[
              { header: 'Domain', accessor: 'domain' },
              { header: 'Status', accessor: 'status', cell: (s: string) => <Badge variant={s === 'verified' ? 'success' : 'warning'}>{s}</Badge> },
              { header: 'SPF', accessor: 'spf', cell: (v: boolean) => <Badge variant={v ? 'success' : 'destructive'}>{v ? 'Valid' : 'Invalid'}</Badge> },
              { header: 'DKIM', accessor: 'dkim', cell: (v: boolean) => <Badge variant={v ? 'success' : 'destructive'}>{v ? 'Valid' : 'Invalid'}</Badge> },
              { header: 'DMARC', accessor: 'dmarc', cell: (v: boolean) => <Badge variant={v ? 'success' : 'destructive'}>{v ? 'Valid' : 'Invalid'}</Badge> },
            ]}
            data={domains}
            keyAccessor="domain"
          />
        </CardContent>
      </Card>
    </div>
  );
}

function WebhookSettings() {
  const [webhooks] = useState([
    { id: 1, url: 'https://app.example.com/webhooks/email', events: ['email.delivered', 'email.opened', 'email.clicked'], active: true },
  ]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <CardTitle className="text-lg">Webhooks</CardTitle>
        <Button>Create Webhook</Button>
      </div>
      <Card>
        <CardContent className="p-0">
          <Table
            columns={[
              { header: 'URL', accessor: 'url' },
              { header: 'Events', accessor: 'events', cell: (e: string[]) => <span className="text-sm">{e.join(', ')}</span> },
              { header: 'Status', accessor: 'active', cell: (a: boolean) => <Badge variant={a ? 'success' : 'secondary'}>{a ? 'Active' : 'Inactive'}</Badge> },
            ]}
            data={webhooks}
            keyAccessor="id"
          />
        </CardContent>
      </Card>
    </div>
  );
}

function ApiKeySettings() {
  const [apiKeys] = useState([
    { id: 1, name: 'Production API', prefix: 'esk_live_', permissions: ['read', 'write'], lastUsed: '2 hours ago', created: '2024-01-15' },
    { id: 2, name: 'Development', prefix: 'esk_test_', permissions: ['read'], lastUsed: 'Never', created: '2024-01-10' },
  ]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <CardTitle className="text-lg">API Keys</CardTitle>
        <Button>Create API Key</Button>
      </div>
      <Card>
        <CardContent className="p-0">
          <Table
            columns={[
              { header: 'Name', accessor: 'name' },
              { header: 'Prefix', accessor: 'prefix' },
              { header: 'Permissions', accessor: 'permissions', cell: (p: string[]) => <span className="text-sm">{p.join(', ')}</span> },
              { header: 'Last Used', accessor: 'lastUsed' },
              { header: 'Created', accessor: 'created' },
            ]}
            data={apiKeys}
            keyAccessor="id"
          />
        </CardContent>
      </Card>
    </div>
  );
}

function TeamSettings() {
  const [members] = useState([
    { id: 1, name: 'John Doe', email: 'john@example.com', role: 'OWNER', joined: '2024-01-01' },
    { id: 2, name: 'Jane Smith', email: 'jane@example.com', role: 'ADMIN', joined: '2024-01-15' },
    { id: 3, name: 'Bob Wilson', email: 'bob@example.com', role: 'MEMBER', joined: '2024-02-01' },
  ]);

  const roleColors = { OWNER: 'purple', ADMIN: 'blue', MANAGER: 'green', MEMBER: 'gray', VIEWER: 'slate' };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <CardTitle className="text-lg">Team Members</CardTitle>
        <Button>Invite Member</Button>
      </div>
      <Card>
        <CardContent className="p-0">
          <Table
            columns={[
              { header: 'Member', accessor: 'member', cell: (row: any) => (
                <div>
                  <p className="font-medium">{row.name}</p>
                  <p className="text-sm text-gray-500">{row.email}</p>
                </div>
              )},
              { header: 'Role', accessor: 'role', cell: (r: string) => <Badge variant={roleColors[r as keyof typeof roleColors] as any}>{r}</Badge> },
              { header: 'Joined', accessor: 'joined' },
            ]}
            data={members}
            keyAccessor="id"
          />
        </CardContent>
      </Card>
    </div>
  );
}

function AuditLogSettings() {
  const [logs] = useState([
    { id: 1, action: 'campaign:sent', entity: 'Campaign', user: 'John Doe', time: '2 hours ago' },
    { id: 2, action: 'contact:created', entity: 'Contact', user: 'Jane Smith', time: '3 hours ago' },
    { id: 3, action: 'settings:updated', entity: 'Settings', user: 'John Doe', time: '5 hours ago' },
  ]);

  return (
    <Card>
      <CardContent className="p-0">
        <Table
          columns={[
            { header: 'Action', accessor: 'action' },
            { header: 'Entity', accessor: 'entity' },
            { header: 'User', accessor: 'user' },
            { header: 'Time', accessor: 'time' },
          ]}
          data={logs}
          keyAccessor="id"
        />
      </CardContent>
    </Card>
  );
}