import React, { useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Mail, Building2, Phone, MapPin, Tag, Send, Clock, Trash2, Edit } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Badge, Table } from '@email-orchestrator/ui-components';

const mockContact = {
  id: 1,
  email: 'john.doe@example.com',
  name: 'John Doe',
  company: 'Acme Corp',
  role: 'CEO',
  phone: '+1 555 0100',
  location: 'San Francisco, CA',
  status: 'active',
  tags: ['decision-maker', 'vip'],
  createdAt: '2024-01-15',
  lastContactedAt: '2024-02-02',
};

const mockActivity = [
  { id: 1, type: 'sent', subject: 'Quick question about Acme', date: '2024-02-02', status: 'delivered' },
  { id: 2, type: 'opened', subject: 'Quick question about Acme', date: '2024-02-02', status: 'opened' },
  { id: 3, type: 'replied', subject: 'Re: Quick question about Acme', date: '2024-02-03', status: 'replied' },
];

export function ContactDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [notes, setNotes] = useState('');

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" onClick={() => navigate('/contacts')}>
            <ArrowLeft className="w-4 h-4" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{mockContact.name}</h1>
            <p className="text-gray-600">{mockContact.email}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline">
            <Edit className="w-4 h-4 mr-2" />
            Edit
          </Button>
          <Button>
            <Send className="w-4 h-4 mr-2" />
            Send Email
          </Button>
          <Button variant="outline" className="text-red-600 hover:bg-red-50">
            <Trash2 className="w-4 h-4 mr-2" />
            Delete
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-lg">Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex items-center gap-2 text-gray-700">
              <Mail className="w-4 h-4 text-gray-400" />
              {mockContact.email}
            </div>
            <div className="flex items-center gap-2 text-gray-700">
              <Building2 className="w-4 h-4 text-gray-400" />
              {mockContact.company} • {mockContact.role}
            </div>
            <div className="flex items-center gap-2 text-gray-700">
              <Phone className="w-4 h-4 text-gray-400" />
              {mockContact.phone}
            </div>
            <div className="flex items-center gap-2 text-gray-700">
              <MapPin className="w-4 h-4 text-gray-400" />
              {mockContact.location}
            </div>
            <div className="flex items-center gap-2 text-gray-700">
              <Tag className="w-4 h-4 text-gray-400" />
              <div className="flex flex-wrap gap-1">
                {mockContact.tags.map(tag => (
                  <Badge key={tag} variant="outline" className="text-xs">{tag}</Badge>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-2 text-gray-700">
              <Clock className="w-4 h-4 text-gray-400" />
              Last contacted {mockContact.lastContactedAt}
            </div>
            <p className="pt-2 text-xs text-gray-500">Contact ID: {id ?? mockContact.id}</p>
          </CardContent>
        </Card>

        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Activity</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table
                columns={[
                  { header: 'Type', accessor: 'type', cell: (type: string) => <Badge variant="outline" className="capitalize">{type}</Badge> },
                  { header: 'Subject', accessor: 'subject' },
                  { header: 'Date', accessor: 'date' },
                  { header: 'Status', accessor: 'status' },
                ]}
                data={mockActivity}
                keyAccessor="id"
                emptyMessage="No activity yet"
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Notes</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <textarea
                className="w-full rounded-md border border-gray-300 p-3 text-sm"
                rows={4}
                placeholder="Add a note about this contact..."
                value={notes}
                onChange={e => setNotes(e.target.value)}
              />
              <div className="flex justify-end">
                <Button disabled={!notes.trim()}>Save Note</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
