import React, { useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { Search, Plus, Download, Upload, Filter, MoreHorizontal, Trash2, Edit, Folder, Users } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Badge, Table, Select, Modal } from '@email-orchestrator/ui-components';

// Mock data for demonstration
const mockList = {
  id: 1,
  name: 'Newsletter Subscribers',
  description: 'All contacts subscribed to our newsletter',
  folder: 'Marketing',
  isPublic: false,
  color: '#3b82f6',
  contactCount: 1250,
  createdAt: '2024-01-15',
};

const mockContacts = [
  { id: 1, email: 'john.doe@example.com', name: 'John Doe', company: 'Acme Corp', role: 'CEO', tags: ['decision-maker', 'vip'] },
  { id: 2, email: 'jane.smith@techstart.io', name: 'Jane Smith', company: 'TechStart', role: 'CTO', tags: ['technical'] },
  { id: 3, email: 'bob.wilson@globalinc.com', name: 'Bob Wilson', company: 'Global Inc', role: 'VP Sales', tags: ['sales'] },
  { id: 4, email: 'alice.brown@innovate.co', name: 'Alice Brown', company: 'Innovate Co', role: 'Founder', tags: ['founder'] },
  { id: 5, email: 'charlie.davis@megacorp.com', name: 'Charlie Davis', company: 'MegaCorp', role: 'Director', tags: ['decision-maker'] },
];

export function ListDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [showAddContacts, setShowAddContacts] = useState(false);
  const [showEdit, setShowEdit] = useState(false);

  const handleDelete = async () => {
    // TODO: Implement delete
    navigate('/lists');
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{mockList.name}</h1>
          <p className="text-gray-600">
            {mockList.contactCount} contacts • {mockList.folder && `Folder: ${mockList.folder}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => setShowEdit(true)}>
            <Edit className="w-4 h-4 mr-2" />
            Edit
          </Button>
          <Button variant="outline">
            <Download className="w-4 h-4 mr-2" />
            Export
          </Button>
          <Button variant="outline" className="text-red-600 hover:bg-red-50">
            <Trash2 className="w-4 h-4 mr-2" />
            Delete
          </Button>
        </div>
      </div>

      {/* List Info Card */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className="w-4 h-4 rounded-full"
                style={{ backgroundColor: mockList.color }}
              />
              <div>
                <p className="text-sm text-gray-600">Color tag</p>
                <p className="font-medium">Used for filtering and organization</p>
              </div>
            </div>
            <Badge variant="outline" style={{ backgroundColor: mockList.color + '20', color: mockList.color }}>
              {mockList.name}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Search and Actions */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <Input
                placeholder="Search contacts in this list..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-10"
              />
            </div>
            <Button variant="outline" onClick={() => setShowAddContacts(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Add Contacts
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Contacts Table */}
      <Card>
        <CardHeader>
          <CardTitle>Contacts ({mockContacts.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table
            columns={[
              { header: 'Contact', accessor: 'name', cell: (name: string, row: any) => (
                <Link to={`/contacts/${row.id}`} className="font-medium text-gray-900 hover:text-primary">
                  {name || row.email}
                </Link>
              )},
              { header: 'Email', accessor: 'email' },
              { header: 'Company', accessor: 'company' },
              { header: 'Role', accessor: 'role' },
              { header: 'Tags', accessor: 'tags', cell: (tags: string[]) => (
                <div className="flex flex-wrap gap-1">
                  {tags.map(tag => (
                    <Badge key={tag} variant="outline" className="text-xs">{tag}</Badge>
                  ))}
                </div>
              )},
            ]}
            data={mockContacts}
            keyAccessor="id"
            emptyMessage="No contacts in this list"
          />
        </CardContent>
      </Card>

      {/* Edit Modal */}
      <Modal
        open={showEdit}
        onOpenChange={setShowEdit}
        title="Edit List"
        description="Update list details"
        size="md"
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">List Name</label>
            <Input defaultValue={mockList.name} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <Input defaultValue={mockList.description} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Folder</label>
            <Select
              placeholder="Select folder"
              options={[
                { value: 'marketing', label: 'Marketing' },
                { value: 'sales', label: 'Sales Prospects' },
                { value: 'customers', label: 'Customers' },
                { value: '', label: 'Uncategorized' },
              ]}
            />
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="outline" onClick={() => setShowEdit(false)}>
              Cancel
            </Button>
            <Button>Save Changes</Button>
          </div>
        </div>
      </Modal>

      {/* Add Contacts Modal */}
      {showAddContacts && (
        <Modal
          open={showAddContacts}
          onOpenChange={setShowAddContacts}
          title="Add Contacts"
          description="Add contacts to this list from your database"
          size="lg"
        >
          <div className="space-y-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <Input placeholder="Search contacts..." className="pl-10" />
            </div>
            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={() => setShowAddContacts(false)}>
                Cancel
              </Button>
              <Button>Add Selected Contacts</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}