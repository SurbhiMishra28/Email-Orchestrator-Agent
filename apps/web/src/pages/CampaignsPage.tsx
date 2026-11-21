import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Search, Send, Clock, CheckCircle, XCircle, AlertCircle, Edit, Trash2, BarChart2 } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Badge, Table, Select } from '@email-orchestrator/ui-components';

const mockCampaigns = [
  { id: 1, name: 'Q4 Product Launch', type: 'regular', status: 'sent', sent: '2 hours ago', delivered: 1250, opened: 532, clicked: 89, replied: 23, bounced: 5 },
  { id: 2, name: 'Black Friday Sale', type: 'regular', status: 'scheduled', sent: 'Tomorrow 10:00', delivered: 0, opened: 0, clicked: 0, replied: 0, bounced: 0 },
  { id: 3, name: 'A/B Test: Subject Lines', type: 'ab_test', status: 'running', sent: '1 hour ago', delivered: 500, opened: 187, clicked: 34, replied: 8, bounced: 2 },
  { id: 4, name: 'Welcome Sequence', type: 'automated', status: 'active', sent: 'Ongoing', delivered: 3421, opened: 1456, clicked: 234, replied: 67, bounced: 12 },
  { id: 5, name: 'Weekly Newsletter #42', type: 'regular', status: 'draft', sent: '—', delivered: 0, opened: 0, clicked: 0, replied: 0, bounced: 0 },
];

const statusConfig = {
  sent: { label: 'Sent', variant: 'success' as const, icon: CheckCircle },
  scheduled: { label: 'Scheduled', variant: 'default' as const, icon: Clock },
  draft: { label: 'Draft', variant: 'secondary' as const, icon: Edit },
  active: { label: 'Active', variant: 'default' as const, icon: CheckCircle },
  running: { label: 'Running', variant: 'default' as const, icon: AlertCircle },
  paused: { label: 'Paused', variant: 'outline' as const, icon: Clock },
  cancelled: { label: 'Cancelled', variant: 'destructive' as const, icon: XCircle },
};

export function CampaignsPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Campaigns</h1>
          <p className="text-gray-600">Create and manage email campaigns</p>
        </div>
        <Button asChild>
          <Link to="/campaigns/new">
            <Plus className="w-4 h-4 mr-2" />
            Create Campaign
          </Link>
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <Input placeholder="Search campaigns..." value={search} onChange={e => setSearch(e.target.value)} className="pl-10" />
            </div>
            <Select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} options={[
              { value: 'all', label: 'All Status' },
              { value: 'draft', label: 'Draft' },
              { value: 'scheduled', label: 'Scheduled' },
              { value: 'sent', label: 'Sent' },
              { value: 'active', label: 'Active' },
            ]} />
            <Select value={typeFilter} onChange={e => setTypeFilter(e.target.value)} options={[
              { value: 'all', label: 'All Types' },
              { value: 'regular', label: 'Regular' },
              { value: 'ab_test', label: 'A/B Test' },
              { value: 'automated', label: 'Automated' },
            ]} />
          </div>
        </CardContent>
      </Card>

      {/* Campaigns Table */}
      <Card>
        <CardContent className="p-0">
          <Table
            columns={[
              { header: 'Campaign', accessor: 'name', cell: (row: any) => (
                <Link to={`/campaigns/${row.id}`} className="font-medium text-gray-900 hover:text-primary">
                  {row.name}
                </Link>
              )},
              { header: 'Type', accessor: 'type', cell: (type: string) => (
                <Badge variant="outline" className="capitalize">{type.replace('_', ' ')}</Badge>
              )},
              { header: 'Status', accessor: 'status', cell: (status: string) => {
                const config = statusConfig[status as keyof typeof statusConfig] || { label: status, variant: 'outline' as const };
                return <Badge variant={config.variant}>{config.label}</Badge>;
              }},
              { header: 'Sent', accessor: 'sent' },
              { header: 'Delivered', accessor: 'delivered', cell: (v: number) => <span className="text-right">{v.toLocaleString()}</span> },
              { header: 'Opened', accessor: 'opened', cell: (v: number) => <span className="text-right">{v.toLocaleString()}</span> },
              { header: 'Clicked', accessor: 'clicked', cell: (v: number) => <span className="text-right">{v.toLocaleString()}</span> },
              { header: 'Replied', accessor: 'replied', cell: (v: number) => <span className="text-right">{v.toLocaleString()}</span> },
              { header: 'Bounced', accessor: 'bounced', cell: (v: number) => <span className="text-right text-red-600">{v.toLocaleString()}</span> },
            ]}
            data={mockCampaigns
              .filter(c => statusFilter === 'all' || c.status === statusFilter)
              .filter(c => typeFilter === 'all' || c.type === typeFilter)
              .filter(c => c.name.toLowerCase().includes(search.toLowerCase()))}
            keyAccessor="id"
            emptyMessage="No campaigns found"
          />
        </CardContent>
      </Card>
    </div>
  );
}