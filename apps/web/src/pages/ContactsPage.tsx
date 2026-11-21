import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, Plus, Download, Upload, Filter, MoreHorizontal, Mail, Tag, Building2, User, Folder, Users, X } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Badge, Table, Select, Modal } from '@email-orchestrator/ui-components';

const mockContacts = [
  { id: 1, email: 'john.doe@acme.com', name: 'John Doe', company: 'Acme Corp', role: 'CEO', tags: ['decision-maker', 'enterprise'], eligible: true },
  { id: 2, email: 'jane.smith@techstart.io', name: 'Jane Smith', company: 'TechStart', role: 'CTO', tags: ['technical', 'startup'], eligible: true },
  { id: 3, email: 'bob.wilson@globalinc.com', name: 'Bob Wilson', company: 'Global Inc', role: 'VP Sales', tags: ['sales', 'enterprise'], eligible: false },
  { id: 4, email: 'alice.brown@innovate.co', name: 'Alice Brown', company: 'Innovate Co', role: 'Founder', tags: ['founder', 'startup'], eligible: true },
  { id: 5, email: 'charlie.davis@megacorp.com', name: 'Charlie Davis', company: 'MegaCorp', role: 'Director', tags: ['decision-maker'], eligible: true },
  { id: 6, email: 'david.lee@startups.io', name: 'David Lee', company: 'Startups.io', role: 'Co-founder', tags: ['founder', 'technical'], eligible: true },
  { id: 7, email: 'emma.watson@globalinc.com', name: 'Emma Watson', company: 'Global Inc', role: 'HR Director', tags: ['hr', 'enterprise'], eligible: true },
];

// Mock data for lists and segments
const mockLists = [
  { id: 1, name: 'Newsletter Subscribers', color: '#3b82f6', contactCount: 1250 },
  { id: 2, name: 'High Value Leads', color: '#ef4444', contactCount: 85 },
  { id: 3, name: 'Enterprise Accounts', color: '#22c55e', contactCount: 42 },
];

const mockSegments = [
  { id: 1, name: 'Active Prospects', contactCount: 150 },
  { id: 2, name: 'Bounced Emails', contactCount: 23 },
  { id: 3, name: 'Recent Opens', contactCount: 89 },
  { id: 4, name: 'Clicked Links', contactCount: 67 },
];

const allTags = ['decision-maker', 'technical', 'sales', 'founder', 'enterprise', 'startup', 'hr'];

export function ContactsPage() {
  const [search, setSearch] = useState('');
  const [selectedContacts, setSelectedContacts] = useState<Set<number>>(new Set());
  const [showImport, setShowImport] = useState(false);
  const [showAddTagModal, setShowAddTagModal] = useState(false);
  const [tagToContact, setTagToContact] = useState<{ contactId: number; tags: string[] } | null>(null);
  const [filterType, setFilterType] = useState<'all' | 'list' | 'segment'>('all');
  const [selectedListId, setSelectedListId] = useState('');
  const [selectedSegmentId, setSelectedSegmentId] = useState('');
  const [contacts, setContacts] = useState(mockContacts);

  const handleSelectionChange = (selected: Set<string | number>) => {
    setSelectedContacts(new Set(Array.from(selected).map(Number)));
  };

  // Build list options for filter select
  const listOptions = [
    { value: '', label: 'All contacts' },
    ...mockLists.map(list => ({
      value: `list_${list.id}`,
      label: `${list.name} (${list.contactCount})`,
    })),
  ];

  // Build segment options for filter select
  const segmentOptions = [
    { value: '', label: 'All contacts' },
    ...mockSegments.map(segment => ({
      value: `segment_${segment.id}`,
      label: `${segment.name} (${segment.contactCount})`,
    })),
  ];

  const handleAddTag = (contactId: number, currentTags: string[], newTag: string) => {
    if (!currentTags.includes(newTag)) {
      console.log('Add tag:', newTag, 'to contact:', contactId);
    }
  };

  // Define columns with access to contacts state for tag removal
  const columns = [
    { header: 'Contact', accessor: 'contact', cell: (row: any) => (
      <div className="flex items-center gap-2">
        <Link to={`/contacts/${row.id}`} className="font-medium text-gray-900 hover:text-primary">
          {row.name || row.email}
        </Link>
      </div>
    )},
    { header: 'Email', accessor: 'email' },
    { header: 'Company', accessor: 'company' },
    { header: 'Role', accessor: 'role' },
    { header: 'Tags', accessor: 'tags', cell: (tags: string[], row: any) => {
      const handleRemoveTag = (tag: string) => {
        const contact = contacts.find(c => c.id === row.id);
        if (contact) {
          const updatedContact = {
            ...contact,
            tags: contact.tags.filter(t => t !== tag)
          };
          setContacts(prev => prev.map(c => c.id === row.id ? updatedContact : c));
          console.log('Tag removed:', tag, 'from contact:', row.id);
        }
      };
      return (
        <div className="flex flex-wrap gap-1.5 items-center">
          {tags.map(tag => (
            <TagItem
              key={tag}
              tag={tag}
              onRemove={() => handleRemoveTag(tag)}
            />
          ))}
        </div>
      );
    }},
    { header: 'Status', accessor: 'eligible', cell: (eligible: boolean) => (
      <Badge variant={eligible ? 'success' : 'destructive'}>
        {eligible ? 'Eligible' : 'Suppressed'}
      </Badge>
    )},
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Contacts</h1>
          <p className="text-gray-600">Manage your contact database</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => setShowImport(true)}>
            <Upload className="w-4 h-4 mr-2" />
            Import
          </Button>
          <Button variant="outline" asChild>
            <Link to="/lists">
              <Users className="w-4 h-4 mr-2" />
              Custom Lists
            </Link>
          </Button>
          <Button variant="outline">
            <Download className="w-4 h-4 mr-2" />
            Export
          </Button>
          <Button asChild>
            <Link to="/contacts/new">
              <Plus className="w-4 h-4 mr-2" />
              Add Contact
            </Link>
          </Button>
        </div>
      </div>

      {/* Search and Filters - Aligned Row */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-4">
            {/* Search - takes full width on small screens */}
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <Input
                placeholder="Search contacts..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-10"
              />
            </div>
            
            {/* Filters Row - properly aligned */}
            <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
              <Select
                placeholder="Filter by..."
                options={[
                  { value: 'all', label: 'All filters' },
                  { value: 'list', label: 'Custom Lists' },
                  { value: 'segment', label: 'Segments' },
                ]}
                value={filterType}
                onChange={e => setFilterType(e.target.value as any)}
                className="min-w-[140px]"
              />
              
              {filterType === 'list' && (
                <Select
                  placeholder="Select list"
                  options={listOptions}
                  value={selectedListId}
                  onChange={e => setSelectedListId(e.target.value)}
                  className="min-w-[160px]"
                />
              )}
              
              {filterType === 'segment' && (
                <Select
                  placeholder="Select segment"
                  options={segmentOptions}
                  value={selectedSegmentId}
                  onChange={e => setSelectedSegmentId(e.target.value)}
                  className="min-w-[160px]"
                />
              )}
              
              <Select
                placeholder="All tags"
                options={[
                  { value: '', label: 'All tags' },
                  ...allTags.map(tag => ({
                    value: tag,
                    label: tag.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '),
                  })),
                ]}
                className="min-w-[160px]"
              />
              
              <Select
                placeholder="All status"
                options={[
                  { value: '', label: 'All status' },
                  { value: 'eligible', label: 'Eligible to email' },
                  { value: 'suppressed', label: 'Suppressed' },
                ]}
                className="min-w-[140px]"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Contacts Table */}
      <Card>
        <CardContent className="p-0">
          {selectedContacts.size > 0 && (
            <div className="px-4 py-3 bg-primary/5 border-b border-primary/20 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <span className="text-sm font-medium text-primary">
                {selectedContacts.size} contact{selectedContacts.size > 1 ? 's' : ''} selected
              </span>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm">Add Tag</Button>
                <Button variant="outline" size="sm" className="text-red-600 hover:bg-red-50">
                  Suppress
                </Button>
                <Button variant="outline" size="sm">Verify Emails</Button>
                <Link to="/lists/new">
                  <Button variant="outline" size="sm">
                    <Plus className="w-4 h-4 mr-1" />
                    Add to List
                  </Button>
                </Link>
              </div>
            </div>
          )}
          <Table
            columns={columns}
            data={contacts}
            keyAccessor="id"
            selectedRows={selectedContacts}
            onSelectionChange={handleSelectionChange}
            emptyMessage="No contacts found"
          />
        </CardContent>
      </Card>

      {/* Import Modal */}
      {showImport && (
        <ImportModal onClose={() => setShowImport(false)} />
      )}

      {/* Add Tag Modal */}
      {showAddTagModal && tagToContact && (
        <Modal
          open={showAddTagModal}
          onOpenChange={setShowAddTagModal}
          title="Add Tag to Contact"
          description="Select tags to add"
          size="md"
        >
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Available Tags</label>
              <div className="flex flex-wrap gap-2">
                {allTags.map(tag => (
                  <label key={tag} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={tagToContact.tags.includes(tag)}
                      onChange={() => handleAddTag(tagToContact.contactId, tagToContact.tags, tag)}
                      className="rounded border-gray-300 text-primary focus:ring-primary"
                    />
                    <Badge variant="outline" className="text-xs">{tag}</Badge>
                  </label>
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-4 border-t">
              <Button variant="outline" onClick={() => setShowAddTagModal(false)}>
                Cancel
              </Button>
              <Button>Apply Tags</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

// Custom Tag component with remove button
interface TagItemProps {
  tag: string;
  onRemove: () => void;
}

function TagItem({ tag, onRemove }: TagItemProps) {
  return (
    <div className="inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded-full border bg-secondary/50 border-secondary hover:bg-secondary/10 transition-colors">
      <span className="text-gray-700">{tag}</span>
      <button
        onClick={onRemove}
        className="rounded-full p-0.5 hover:bg-gray-200 text-gray-500 hover:text-gray-700 transition-colors"
        aria-label={`Remove tag ${tag}`}
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}

function ImportModal({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(1);
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold">Import Contacts</h2>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded">✕</button>
        </div>
        
        <div className="p-4">
          {step === 1 && (
            <div className="space-y-4">
              <p className="text-gray-600">Upload a CSV file with your contacts. Required columns: email. Optional: name, company, role, tags.</p>
              <div
                className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-primary transition-colors"
                onDragOver={e => e.preventDefault()}
                onDrop={e => { e.preventDefault(); setFile(e.dataTransfer.files[0]); }}
              >
                <Upload className="w-12 h-12 mx-auto text-gray-400 mb-2" />
                <p>Drag & drop CSV file or click to browse</p>
                <input
                  type="file"
                  accept=".csv"
                  className="hidden"
                  id="csv-upload"
                  onChange={e => setFile(e.target.files?.[0] ?? null)}
                />
                <label htmlFor="csv-upload" className="text-primary hover:underline cursor-pointer">Browse files</label>
              </div>
              {file && (
                <Button onClick={() => setStep(2)} className="w-full">
                  Continue with {file.name}
                </Button>
              )}
            </div>
          )}
          
          {step === 2 && (
            <div className="space-y-4">
              <h3 className="font-medium">Map Columns</h3>
              <p className="text-sm text-gray-600">Match your CSV columns to contact fields</p>
              <div className="space-y-3 max-h-64 overflow-y-auto">
                {['email', 'name', 'company', 'role', 'tags'].map(field => (
                  <div key={field} className="flex items-center gap-3">
                    <label className="w-32 text-sm font-medium capitalize">{field}</label>
                    <Select
                      placeholder="Ignore"
                      options={[
                        { value: '', label: 'Ignore' },
                        { value: 'email', label: 'Email' },
                        { value: 'name', label: 'Name' },
                        { value: 'company', label: 'Company' },
                        { value: 'role', label: 'Role' },
                        { value: 'tags', label: 'Tags (semicolon-separated)' },
                      ]}
                      value={mapping[field]}
                      onChange={e => setMapping(prev => ({ ...prev, [field]: e.target.value }))}
                    />
                  </div>
                ))}
              </div>
              <div className="flex justify-end gap-2 pt-4 border-t">
                <Button variant="outline" onClick={() => setStep(1)}>Back</Button>
                <Button onClick={() => setStep(3)}>Import</Button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="text-center py-8">
              <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold">Import Complete</h3>
              <p className="text-gray-600 mt-2">Successfully imported contacts</p>
              <Button onClick={onClose} className="mt-4 w-full sm:w-auto">Done</Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}