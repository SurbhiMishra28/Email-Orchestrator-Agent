import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Folder, Palette } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Button, Input } from '@email-orchestrator/ui-components';

const colors = [
  { value: '#3b82f6', label: 'Blue' },
  { value: '#ef4444', label: 'Red' },
  { value: '#22c55e', label: 'Green' },
  { value: '#f59e0b', label: 'Amber' },
  { value: '#8b5cf6', label: 'Violet' },
  { value: '#ec4899', label: 'Pink' },
  { value: '#14b8a6', label: 'Teal' },
  { value: '#f97316', label: 'Orange' },
];

export function CreateFolderPage() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [parentFolderId, setParentFolderId] = useState('');
  const [color, setColor] = useState('#3b82f6');

  const handleCreate = async () => {
    // TODO: Implement actual folder creation via API
    navigate('/lists');
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Create Folder</h1>
        <p className="text-gray-600">Organize your lists into folders</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Folder Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Folder Name <span className="text-red-500">*</span>
            </label>
            <Input
              placeholder="e.g., Marketing Campaigns"
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </div>

          {/* Parent Folder */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Folder className="inline w-4 h-4 mr-1" />
              Parent Folder
            </label>
            <select
              value={parentFolderId}
              onChange={e => setParentFolderId(e.target.value)}
              className="mt-2 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary focus:ring-primary sm:text-sm"
            >
              <option value="">No parent (top-level folder)</option>
              <option value="marketing">Marketing</option>
              <option value="sales">Sales Prospects</option>
              <option value="customers">Customers</option>
              <option value="other">Other Folders...</option>
            </select>
          </div>

          {/* Color */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Palette className="inline w-4 h-4 mr-1" />
              Folder Color
            </label>
            <div className="flex flex-wrap gap-2 mt-2">
              {colors.map(c => (
                <button
                  key={c.value}
                  onClick={() => setColor(c.value)}
                  className={`w-8 h-8 rounded-full border-2 ${color === c.value ? 'border-gray-900' : 'border-gray-300'} ${c.value === '#3b82f6' ? 'bg-blue-500' : color === '#ef4444' ? 'bg-red-500' : color === '#22c55e' ? 'bg-green-500' : color === '#f59e0b' ? 'bg-amber-500' : color === '#8b5cf6' ? 'bg-violet-500' : color === '#ec4899' ? 'bg-pink-500' : color === '#14b8a6' ? 'bg-teal-500' : color === '#f97316' ? 'bg-orange-500' : 'bg-blue-500'}`}
                  title={c.label}
                />
              ))}
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-4 pt-4 border-t">
            <Button variant="outline" onClick={() => navigate('/lists')}>
              Cancel
            </Button>
            <Button onClick={handleCreate}>Create Folder</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}