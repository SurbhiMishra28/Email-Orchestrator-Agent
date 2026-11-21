import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Search, Edit, Trash2, Copy, Check, X, Mail, Type } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Badge, Table, Select } from '@email-orchestrator/ui-components';

const mockTemplates = [
  { id: 1, name: 'Cold Outreach v1', category: 'intro', subject: 'Quick question about {{company}}', active: true, used: 45, created: '2024-01-15' },
  { id: 2, name: 'Follow-up Sequence', category: 'follow_up', subject: 'Following up on my previous email', active: true, used: 32, created: '2024-01-10' },
  { id: 3, name: 'Newsletter Template', category: 'newsletter', subject: 'Weekly Update - {{date}}', active: false, used: 12, created: '2024-01-05' },
  { id: 4, name: 'Product Announcement', category: 'promotional', subject: 'Introducing our new feature', active: true, used: 8, created: '2024-01-20' },
];

const categories = ['All', 'intro', 'follow_up', 'newsletter', 'promotional', 'transactional', 'custom'];

export function TemplatesPage() {
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('All');
  const [activeFilter, setActiveFilter] = useState('all');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Templates</h1>
          <p className="text-gray-600">Create and manage email templates</p>
        </div>
        <Button asChild>
          <Link to="/templates/new">
            <Plus className="w-4 h-4 mr-2" />
            Create Template
          </Link>
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <Input placeholder="Search templates..." value={search} onChange={e => setSearch(e.target.value)} className="pl-10" />
            </div>
            <Select value={category} onChange={e => setCategory(e.target.value)} options={categories.map(c => ({ value: c, label: c }))} />
            <Select value={activeFilter} onChange={e => setActiveFilter(e.target.value)} options={[
              { value: 'all', label: 'All' },
              { value: 'active', label: 'Active' },
              { value: 'inactive', label: 'Inactive' },
            ]} />
          </div>
        </CardContent>
      </Card>

      {/* Templates Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {mockTemplates
          .filter(t => category === 'All' || t.category === category)
          .filter(t => activeFilter === 'all' || (activeFilter === 'active' && t.active) || (activeFilter === 'inactive' && !t.active))
          .filter(t => t.name.toLowerCase().includes(search.toLowerCase()) || t.subject.toLowerCase().includes(search.toLowerCase()))
          .map(template => (
            <TemplateCard key={template.id} template={template} />
          ))}
      </div>

      {mockTemplates.length === 0 && (
        <Card className="text-center py-12">
          <Mail className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900">No templates yet</h3>
          <p className="text-gray-600 mt-1">Create your first email template to get started</p>
          <Button asChild className="mt-4">
            <Link to="/templates/new">Create Template</Link>
          </Button>
        </Card>
      )}
    </div>
  );
}

function TemplateCard({ template }: { template: typeof mockTemplates[0] }) {
  return (
    <Card className="h-full">
      <CardContent className="p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <Badge variant={template.category === 'intro' ? 'default' : template.category === 'follow_up' ? 'secondary' : 'outline'}>
              {template.category.replace('_', ' ')}
            </Badge>
            <Badge variant={template.active ? 'success' : 'secondary'} className="ml-2">
              {template.active ? 'Active' : 'Draft'}
            </Badge>
          </div>
          <div className="flex gap-1">
            <Button variant="ghost" size="icon" className="h-8 w-8"><Edit className="w-4 h-4" /></Button>
            <Button variant="ghost" size="icon" className="h-8 w-8"><Copy className="w-4 h-4" /></Button>
            <Button variant="ghost" size="icon" className="h-8 w-8 text-red-600 hover:bg-red-50"><Trash2 className="w-4 h-4" /></Button>
          </div>
        </div>
        <h3 className="font-semibold text-gray-900 mb-2">{template.name}</h3>
        <p className="text-sm text-gray-600 mb-4 line-clamp-2">{template.subject}</p>
        <div className="flex items-center justify-between text-sm text-gray-500">
          <span>Used {template.used} times</span>
          <span>Created {template.created}</span>
        </div>
      </CardContent>
    </Card>
  );
}