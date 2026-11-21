import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Send, Pause, Play, Trash2, Users, MousePointerClick, MailOpen, Reply, AlertTriangle } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Button, Badge, Table } from '@email-orchestrator/ui-components';

const mockCampaign = {
  id: 1,
  name: 'Q4 Product Launch',
  type: 'regular',
  status: 'sent',
  subject: 'Introducing our newest product',
  template: 'Cold Outreach v1',
  audience: 'High Value Leads',
  sentAt: '2024-02-01 10:00',
  delivered: 1250,
  opened: 532,
  clicked: 89,
  replied: 23,
  bounced: 5,
};

const mockRecipients = [
  { id: 1, email: 'john.doe@example.com', status: 'delivered', opened: true, clicked: true },
  { id: 2, email: 'jane.smith@techstart.io', status: 'delivered', opened: true, clicked: false },
  { id: 3, email: 'bob.wilson@globalinc.com', status: 'bounced', opened: false, clicked: false },
  { id: 4, email: 'alice.brown@innovate.co', status: 'delivered', opened: false, clicked: false },
];

const stats = [
  { label: 'Delivered', value: mockCampaign.delivered, icon: Send },
  { label: 'Opened', value: mockCampaign.opened, icon: MailOpen },
  { label: 'Clicked', value: mockCampaign.clicked, icon: MousePointerClick },
  { label: 'Replied', value: mockCampaign.replied, icon: Reply },
  { label: 'Bounced', value: mockCampaign.bounced, icon: AlertTriangle },
];

export function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [status, setStatus] = useState(mockCampaign.status);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" onClick={() => navigate('/campaigns')}>
            <ArrowLeft className="w-4 h-4" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{mockCampaign.name}</h1>
            <p className="text-gray-600 capitalize">{mockCampaign.type.replace('_', ' ')} • {mockCampaign.sentAt}</p>
          </div>
          <Badge variant={status === 'sent' ? 'success' : 'default'} className="capitalize">{status}</Badge>
        </div>
        <div className="flex flex-wrap gap-2">
          {status === 'running' ? (
            <Button variant="outline" onClick={() => setStatus('paused')}>
              <Pause className="w-4 h-4 mr-2" />
              Pause
            </Button>
          ) : (
            <Button variant="outline" onClick={() => setStatus('running')}>
              <Play className="w-4 h-4 mr-2" />
              Resume
            </Button>
          )}
          <Button variant="outline" className="text-red-600 hover:bg-red-50">
            <Trash2 className="w-4 h-4 mr-2" />
            Delete
          </Button>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {stats.map(stat => (
          <Card key={stat.label}>
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">{stat.label}</p>
                  <p className="mt-1 text-2xl font-bold text-gray-900">{stat.value.toLocaleString()}</p>
                </div>
                <div className="p-2.5 bg-primary/10 rounded-lg">
                  <stat.icon className="w-5 h-5 text-primary" />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Campaign Settings</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3 text-sm">
          <div>
            <p className="text-gray-500">Subject</p>
            <p className="font-medium text-gray-900">{mockCampaign.subject}</p>
          </div>
          <div>
            <p className="text-gray-500">Template</p>
            <p className="font-medium text-gray-900">{mockCampaign.template}</p>
          </div>
          <div>
            <p className="text-gray-500">Audience</p>
            <p className="flex items-center gap-1 font-medium text-gray-900">
              <Users className="w-4 h-4 text-gray-400" />
              {mockCampaign.audience}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Recipients ({mockRecipients.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table
            columns={[
              { header: 'Email', accessor: 'email' },
              {
                header: 'Status',
                accessor: 'status',
                cell: (value: string) => (
                  <Badge variant={value === 'bounced' ? 'destructive' : value === 'delivered' ? 'success' : 'secondary'} className="capitalize">
                    {value}
                  </Badge>
                ),
              },
              { header: 'Opened', accessor: 'opened', cell: (v: boolean) => (v ? 'Yes' : 'No') },
              { header: 'Clicked', accessor: 'clicked', cell: (v: boolean) => (v ? 'Yes' : 'No') },
            ]}
            data={mockRecipients}
            keyAccessor="id"
            emptyMessage="No recipients"
          />
        </CardContent>
      </Card>

      <p className="text-xs text-gray-500">Campaign ID: {id ?? mockCampaign.id}</p>
    </div>
  );
}
