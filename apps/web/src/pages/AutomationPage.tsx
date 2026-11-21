import React, { useState } from 'react';
import { Plus, Play, Pause, Trash2, Edit, Zap, Mail, Clock, GitBranch, Users } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Badge, Table, Modal, Select } from '@email-orchestrator/ui-components';

interface Automation {
  id: number;
  name: string;
  trigger: string;
  steps: number;
  status: 'active' | 'paused' | 'draft';
  enrolled: number;
  completed: number;
  updatedAt: string;
}

const mockAutomations: Automation[] = [
  { id: 1, name: 'Welcome Sequence', trigger: 'contact.created', steps: 4, status: 'active', enrolled: 3421, completed: 2890, updatedAt: '2024-02-01' },
  { id: 2, name: 'No Reply Follow-up', trigger: 'email.no_reply', steps: 3, status: 'active', enrolled: 812, completed: 640, updatedAt: '2024-01-28' },
  { id: 3, name: 'Link Click Nurture', trigger: 'email.clicked', steps: 2, status: 'paused', enrolled: 240, completed: 128, updatedAt: '2024-01-15' },
  { id: 4, name: 'Re-engagement', trigger: 'contact.inactive_90d', steps: 5, status: 'draft', enrolled: 0, completed: 0, updatedAt: '2024-02-03' },
];

const statusVariant: Record<Automation['status'], 'success' | 'warning' | 'secondary'> = {
  active: 'success',
  paused: 'warning',
  draft: 'secondary',
};

const triggerOptions = [
  { value: 'contact.created', label: 'Contact created' },
  { value: 'email.opened', label: 'Email opened' },
  { value: 'email.clicked', label: 'Link clicked' },
  { value: 'email.no_reply', label: 'No reply after N days' },
  { value: 'email.replied', label: 'Email replied' },
  { value: 'contact.inactive_90d', label: 'Contact inactive 90 days' },
];

const stepLibrary = [
  { icon: Mail, label: 'Send Email' },
  { icon: Clock, label: 'Wait / Delay' },
  { icon: GitBranch, label: 'Condition' },
  { icon: Users, label: 'Add to List' },
];

export function AutomationPage() {
  const [automations, setAutomations] = useState(mockAutomations);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newTrigger, setNewTrigger] = useState(triggerOptions[0].value);

  const toggleStatus = (id: number) => {
    setAutomations(prev =>
      prev.map(a =>
        a.id === id
          ? { ...a, status: a.status === 'active' ? 'paused' : 'active' }
          : a
      )
    );
  };

  const handleCreate = () => {
    const name = newName.trim() || 'Untitled Automation';
    setAutomations(prev => [
      ...prev,
      {
        id: Math.max(0, ...prev.map(a => a.id)) + 1,
        name,
        trigger: newTrigger,
        steps: 0,
        status: 'draft',
        enrolled: 0,
        completed: 0,
        updatedAt: new Date().toISOString().slice(0, 10),
      },
    ]);
    setNewName('');
    setNewTrigger(triggerOptions[0].value);
    setShowCreate(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Automation</h1>
          <p className="text-gray-600">Trigger-based sequences that run on their own</p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="w-4 h-4 mr-2" />
          New Automation
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stepLibrary.map(step => (
          <Card key={step.label}>
            <CardContent className="flex items-center gap-3 p-4">
              <div className="p-2.5 bg-primary/10 rounded-lg">
                <step.icon className="w-5 h-5 text-primary" />
              </div>
              <span className="text-sm font-medium text-gray-800">{step.label}</span>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Zap className="w-5 h-5 text-gray-400" />
            Automations ({automations.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table
            columns={[
              { header: 'Name', accessor: 'name', cell: (name: string) => <span className="font-medium text-gray-900">{name}</span> },
              { header: 'Trigger', accessor: 'trigger', cell: (trigger: string) => (
                <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-700">{trigger}</code>
              )},
              { header: 'Steps', accessor: 'steps', cell: (v: number) => `${v}` },
              { header: 'Status', accessor: 'status', cell: (status: Automation['status']) => (
                <Badge variant={statusVariant[status]} className="capitalize">{status}</Badge>
              )},
              { header: 'Enrolled', accessor: 'enrolled', cell: (v: number) => v.toLocaleString() },
              { header: 'Completed', accessor: 'completed', cell: (v: number) => v.toLocaleString() },
              { header: 'Updated', accessor: 'updatedAt' },
              { header: '', accessor: 'id', cell: (_v: unknown, row: Automation) => (
                <div className="flex justify-end gap-1">
                  <Button variant="ghost" size="sm" onClick={() => toggleStatus(row.id)}>
                    {row.status === 'active' ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                  </Button>
                  <Button variant="ghost" size="sm"><Edit className="w-4 h-4" /></Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-red-600"
                    onClick={() => setAutomations(prev => prev.filter(a => a.id !== row.id))}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              )},
            ]}
            data={automations}
            keyAccessor="id"
            emptyMessage="No automations yet"
          />
        </CardContent>
      </Card>

      <Modal open={showCreate} onOpenChange={setShowCreate} title="New Automation" description="Pick a trigger to start a new workflow">
        <div className="space-y-4">
          <Input
            label="Automation Name"
            placeholder="e.g. Welcome Sequence"
            value={newName}
            onChange={e => setNewName(e.target.value)}
          />
          <Select
            label="Trigger"
            value={newTrigger}
            onChange={e => setNewTrigger(e.target.value)}
            options={triggerOptions}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={handleCreate}>Create Automation</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
