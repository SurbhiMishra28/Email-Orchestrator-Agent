import React, { useState } from 'react';
import { Search, Plus, Filter, Trash2, Edit, Users } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Badge, Table, Modal, Select } from '@email-orchestrator/ui-components';

const mockSegments = [
  { id: 1, name: 'High Value Leads', description: 'Contacts with score > 80', type: 'dynamic', contactCount: 85, updatedAt: '2024-02-01' },
  { id: 2, name: 'Recently Active', description: 'Opened an email in the last 30 days', type: 'dynamic', contactCount: 1240, updatedAt: '2024-02-03' },
  { id: 3, name: 'Enterprise Accounts', description: 'Company size over 500', type: 'static', contactCount: 42, updatedAt: '2024-01-20' },
  { id: 4, name: 'No Reply Yet', description: 'Contacted but no response', type: 'dynamic', contactCount: 310, updatedAt: '2024-02-02' },
];

export function SegmentsPage() {
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [showCreate, setShowCreate] = useState(false);

  const filtered = mockSegments
    .filter(s => typeFilter === 'all' || s.type === typeFilter)
    .filter(s => s.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Segments</h1>
          <p className="text-gray-600">Group contacts with dynamic rules or static lists</p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="w-4 h-4 mr-2" />
          New Segment
        </Button>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <Input placeholder="Search segments..." value={search} onChange={e => setSearch(e.target.value)} className="pl-10" />
            </div>
            <Select value={typeFilter} onChange={e => setTypeFilter(e.target.value)} options={[
              { value: 'all', label: 'All Types' },
              { value: 'dynamic', label: 'Dynamic' },
              { value: 'static', label: 'Static' },
            ]} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Segments ({filtered.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table
            columns={[
              { header: 'Name', accessor: 'name', cell: (name: string) => <span className="font-medium text-gray-900">{name}</span> },
              { header: 'Description', accessor: 'description' },
              { header: 'Type', accessor: 'type', cell: (type: string) => <Badge variant={type === 'dynamic' ? 'default' : 'outline'} className="capitalize">{type}</Badge> },
              { header: 'Contacts', accessor: 'contactCount', cell: (v: number) => <span className="inline-flex items-center gap-1"><Users className="w-3.5 h-3.5 text-gray-400" />{v.toLocaleString()}</span> },
              { header: 'Updated', accessor: 'updatedAt' },
              { header: '', accessor: 'id', cell: (_v: unknown, row: { id: number }) => (
                <div className="flex justify-end gap-1">
                  <Button variant="ghost" size="sm"><Edit className="w-4 h-4" /></Button>
                  <Button variant="ghost" size="sm" className="text-red-600"><Trash2 className="w-4 h-4" /></Button>
                </div>
              )},
            ]}
            data={filtered}
            keyAccessor="id"
            emptyMessage="No segments found"
          />
        </CardContent>
      </Card>

      <Modal open={showCreate} onOpenChange={setShowCreate} title="New Segment" description="Define who belongs in this segment">
        <div className="space-y-4">
          <Input label="Segment Name" placeholder="e.g. High Value Leads" />
          <Input label="Description" placeholder="What makes this segment unique?" />
          <Select
            label="Type"
            options={[
              { value: 'dynamic', label: 'Dynamic (rules-based)' },
              { value: 'static', label: 'Static (manual)' },
            ]}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={() => setShowCreate(false)}>Create Segment</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
