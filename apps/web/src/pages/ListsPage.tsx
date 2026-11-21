import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, Plus, Filter, MoreHorizontal, Folder, Users, ChevronRight, Trash2, Edit } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Badge, Table, Select, Modal, DropdownMenu } from '@email-orchestrator/ui-components';

// Mock data for demonstration
const mockFolders = [
  { id: 1, name: 'Marketing', color: '#3b82f6', listCount: 5, subfolders: 2 },
  { id: 2, name: 'Sales Prospects', color: '#ef4444', listCount: 3, subfolders: 0 },
  { id: 3, name: 'Customers', color: '#22c55e', listCount: 8, subfolders: 1 },
  { id: 4, name: 'Inactive', color: '#9ca3af', listCount: 2, subfolders: 0 },
];

const mockLists = [
  { id: 1, name: 'Newsletter Subscribers', folder: 'Marketing', contactCount: 1250, color: '#3b82f6' },
  { id: 2, name: 'High Value Leads', folder: 'Sales Prospects', contactCount: 85, color: '#ef4444' },
  { id: 3, name: 'Enterprise Accounts', folder: 'Customers', contactCount: 42, color: '#22c55e' },
  { id: 4, name: 'Trial Users', folder: 'Marketing', contactCount: 230, color: '#8b5cf6' },
  { id: 5, name: 'Product Hunt Launch', folder: null, contactCount: 500, color: '#f59e0b' },
  { id: 6, name: 'VIP Customers', folder: 'Customers', contactCount: 18, color: '#22c55e' },
  { id: 7, name: 'Cold Prospects', folder: 'Sales Prospects', contactCount: 450, color: '#ef4444' },
  { id: 8, name: 'Churned Customers', folder: 'Inactive', contactCount: 65, color: '#9ca3af' },
];

export function ListsPage() {
  const [search, setSearch] = useState('');
  const [selectedFilter, setSelectedFilter] = useState('all');
  const [view, setView] = useState<'folders' | 'lists'>('lists');
  const [showCreateFolder, setShowCreateFolder] = useState(false);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Custom Lists</h1>
          <p className="text-gray-600">Create and organize email lists in folders</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => setView('folders')}>
            <Folder className="w-4 h-4 mr-2" />
            Folders
          </Button>
          <Button variant="outline" onClick={() => setShowCreateFolder(true)}>
            <Folder className="w-4 h-4 mr-2" />
            New Folder
          </Button>
          <Button asChild>
            <Link to="/lists/new">
              <Plus className="w-4 h-4 mr-2" />
              New List
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
                placeholder="Search lists or folders..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-10"
              />
            </div>
            
            {/* Filters Row - properly aligned */}
            <div className="flex items-center gap-3 w-full sm:w-auto flex-wrap">
              <Select
                placeholder="All folders"
                options={[
                  { value: 'all', label: 'All Folders' },
                  { value: 'marketing', label: 'Marketing' },
                  { value: 'sales', label: 'Sales Prospects' },
                  { value: 'customers', label: 'Customers' },
                  { value: 'inactive', label: 'Inactive' },
                ]}
                value={selectedFilter}
                onChange={e => setSelectedFilter(e.target.value)}
                className="min-w-[140px]"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* View Toggle */}
      {view === 'folders' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">Folders</h2>
            <Button variant="outline" onClick={() => setShowCreateFolder(true)}>
              <Plus className="w-4 h-4 mr-2" />
              New Folder
            </Button>
          </div>
          <Card>
            <CardContent className="p-0">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
                {mockFolders.map(folder => (
                  <div
                    key={folder.id}
                    className="border rounded-lg p-4 hover:shadow-sm cursor-pointer"
                    style={{ borderColor: folder.color + '33' }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-3 h-3 rounded-full"
                          style={{ backgroundColor: folder.color }}
                        />
                        <h3 className="font-medium text-gray-900">{folder.name}</h3>
                      </div>
                      <DropdownMenu
                        trigger={<MoreHorizontal className="w-4 h-4 text-gray-400" />}
                        items={[
                          { label: 'Edit', onClick: () => {} },
                          { label: 'Rename', onClick: () => {} },
                          { label: 'Delete', onClick: () => {}, destructive: true },
                        ]}
                      />
                    </div>
                    <div className="text-sm text-gray-600">
                      {folder.listCount} lists
                      {folder.subfolders > 0 && (
                        <span className="ml-2 text-gray-400">· {folder.subfolders} subfolders</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              <div className="border-t p-4">
                <Button variant="outline" className="w-full">
                  View All Folders
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Lists View */}
      {view === 'lists' && (
        <Card>
          <CardContent className="p-0">
            <Table
              columns={[
                { header: 'List', accessor: 'name', cell: (name: string, row: any) => (
                  <div className="flex items-center gap-3">
                    <div
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: row.color }}
                    />
                    <Link to={`/lists/${row.id}`} className="font-medium text-gray-900 hover:text-primary">
                      {name}
                    </Link>
                  </div>
                )},
                { header: 'Folder', accessor: 'folder', cell: (folder: string | null) => (
                  folder ? (
                    <Badge variant="outline" className="text-xs">{folder}</Badge>
                  ) :
                    <span className="text-gray-400 text-sm">Uncategorized</span>
                )},
                { header: 'Contacts', accessor: 'contactCount' },
                { header: '', accessor: 'id', cell: (_: any, row: any) => (
                  <DropdownMenu
                    trigger={<MoreHorizontal className="w-4 h-4 text-gray-400" />}
                    items={[
                      { label: 'Edit', onClick: () => {} },
                      { label: 'View Contacts', onClick: () => {} },
                      { label: 'Delete', onClick: () => {}, destructive: true },
                    ]}
                  />
                )}
              ]}
              data={mockLists}
              keyAccessor="id"
              emptyMessage="No lists found"
            />
            <div className="border-t p-4">
              <Button variant="outline" className="w-full">
                Create New List
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Create Folder Modal */}
      {showCreateFolder && (
        <Modal
          open={showCreateFolder}
          onOpenChange={setShowCreateFolder}
          title="Create Folder"
          description="Organize your lists into folders"
          size="md"
        >
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Folder Name <span className="text-red-500">*</span>
              </label>
              <Input placeholder="e.g., Marketing Campaigns" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Parent Folder (optional)
              </label>
              <Select
                placeholder="No parent (top-level)"
                options={[
                  { value: '', label: 'No parent (top-level)' },
                  { value: 'marketing', label: 'Marketing' },
                  { value: 'sales', label: 'Sales Prospects' },
                ]}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Color
              </label>
              <div className="flex gap-2">
                {['#3b82f6', '#ef4444', '#22c55e', '#f59e0b', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'].map(color => (
                  <button
                    key={color}
                    onClick={() => {}}
                    className="w-8 h-8 rounded-full border-2 border-gray-300"
                    style={{ backgroundColor: color }}
                  />
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-4 border-t">
              <Button variant="outline" onClick={() => setShowCreateFolder(false)}>
                Cancel
              </Button>
              <Button>Create Folder</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}