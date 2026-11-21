import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Folder, Palette } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Textarea, Select } from '@email-orchestrator/ui-components';

const colors = [
  { value: '#3b82f6', label: 'Blue', class: 'bg-blue-500' },
  { value: '#ef4444', label: 'Red', class: 'bg-red-500' },
  { value: '#22c55e', label: 'Green', class: 'bg-green-500' },
  { value: '#f59e0b', label: 'Amber', class: 'bg-amber-500' },
  { value: '#8b5cf6', label: 'Violet', class: 'bg-violet-500' },
  { value: '#ec4899', label: 'Pink', class: 'bg-pink-500' },
  { value: '#14b8a6', label: 'Teal', class: 'bg-teal-500' },
  { value: '#f97316', label: 'Orange', class: 'bg-orange-500' },
];

export function CreateListPage() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [folderId, setFolderId] = useState('');
  const [color, setColor] = useState('#3b82f6');
  const [isPublic, setIsPublic] = useState(false);

  const handleCreate = async () => {
    // TODO: Implement actual list creation via API
    navigate('/lists');
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Create New List</h1>
        <p className="text-gray-600">Organize your contacts into custom lists</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>List Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              List Name <span className="text-red-500">*</span>
            </label>
            <Input
              placeholder="e.g., Newsletter Subscribers"
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <Textarea
              placeholder="Brief description of this list"
              rows={3}
              value={description}
              onChange={e => setDescription(e.target.value)}
            />
          </div>

          {/* Folder */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Folder className="inline w-4 h-4 mr-1" />
              Folder
            </label>
            <Select
              placeholder="Select a folder (optional)"
              options={[
                { value: '', label: 'Uncategorized' },
                { value: 'marketing', label: 'Marketing' },
                { value: 'sales', label: 'Sales Prospects' },
                { value: 'customers', label: 'Customers' },
                { value: 'inactive', label: 'Inactive' },
              ]}
              value={folderId}
              onChange={e => setFolderId(e.target.value)}
            />
          </div>

          {/* Color */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Palette className="inline w-4 h-4 mr-1" />
              List Color
            </label>
            <div className="flex gap-2 mt-2">
              {colors.map(c => (
                <button
                  key={c.value}
                  onClick={() => setColor(c.value)}
                  className={`w-8 h-8 rounded-full border-2 ${color === c.value ? 'border-gray-900' : 'border-gray-300'} ${c.class} relative`}
                  title={c.label}
                >
                  {color === c.value && (
                    <span className="absolute inset-0 flex items-center justify-center">
                      <span className="w-2 h-2 bg-white rounded-full" />
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Privacy */}
          <div className="flex items-center justify-between rounded-md border p-3">
            <div>
              <label className="text-sm font-medium text-gray-700">Public List</label>
              <p className="text-sm text-gray-500">Make this list visible to team members</p>
            </div>
            <button
              type="button"
              onClick={() => setIsPublic(!isPublic)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${isPublic ? 'bg-primary' : 'bg-gray-200'}`}
            >
              <span className={`inline-block h-5 w-5 rounded-full transition-transform ${isPublic ? 'translate-x-5 bg-white' : 'translate-x-1 bg-gray-500'}`} />
            </button>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-4 pt-4 border-t">
            <Button variant="outline" onClick={() => navigate('/lists')}>
              Cancel
            </Button>
            <Button onClick={handleCreate}>Create List</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}