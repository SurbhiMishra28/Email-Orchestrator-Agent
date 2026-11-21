import React, { useState } from 'react';
import { Search, Send, Reply, Archive, Trash2, Star, Paperclip } from 'lucide-react';
import { Card, CardContent, Button, Input, Badge } from '@email-orchestrator/ui-components';

interface Thread {
  id: number;
  from: string;
  subject: string;
  preview: string;
  date: string;
  unread: boolean;
  starred: boolean;
  hasAttachment: boolean;
  tag: 'interested' | 'not-interested' | 'follow-up' | 'ooo';
}

const threads: Thread[] = [
  { id: 1, from: 'John Doe', subject: 'Re: Quick question about Acme', preview: 'Yes, this sounds interesting. Can we set up a call next week?', date: '10:24 AM', unread: true, starred: true, hasAttachment: false, tag: 'interested' },
  { id: 2, from: 'Jane Smith', subject: 'Re: Following up on my previous email', preview: 'Thanks for reaching out. We are not looking right now.', date: '9:02 AM', unread: true, starred: false, hasAttachment: false, tag: 'not-interested' },
  { id: 3, from: 'Bob Wilson', subject: 'Re: Introducing our newest product', preview: 'Please send over the pricing sheet and I will review it.', date: 'Yesterday', unread: false, starred: false, hasAttachment: true, tag: 'follow-up' },
  { id: 4, from: 'Alice Brown', subject: 'Automatic reply: Out of office', preview: 'I am currently out of the office and will return on Monday.', date: 'Yesterday', unread: false, starred: false, hasAttachment: false, tag: 'ooo' },
  { id: 5, from: 'Charlie Davis', subject: 'Re: Partnership opportunity', preview: 'Interesting proposal. Let us discuss the details further.', date: 'Monday', unread: false, starred: true, hasAttachment: false, tag: 'interested' },
];

const tagVariant: Record<Thread['tag'], 'success' | 'destructive' | 'warning' | 'secondary'> = {
  interested: 'success',
  'not-interested': 'destructive',
  'follow-up': 'warning',
  ooo: 'secondary',
};

export function InboxPage() {
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<number>(threads[0].id);

  const filtered = threads.filter(
    t =>
      t.subject.toLowerCase().includes(search.toLowerCase()) ||
      t.from.toLowerCase().includes(search.toLowerCase())
  );
  const selected = threads.find(t => t.id === selectedId) ?? threads[0];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Inbox</h1>
        <p className="text-gray-600">Replies and conversations from your campaigns</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <CardContent className="p-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <Input placeholder="Search inbox..." value={search} onChange={e => setSearch(e.target.value)} className="pl-10" />
            </div>
            <ul className="mt-3 divide-y divide-gray-100">
              {filtered.map(thread => (
                <li key={thread.id}>
                  <button
                    onClick={() => setSelectedId(thread.id)}
                    className={`w-full px-2 py-3 text-left transition-colors hover:bg-gray-50 ${
                      thread.id === selectedId ? 'bg-primary/5' : ''
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className={`truncate text-sm ${thread.unread ? 'font-semibold text-gray-900' : 'text-gray-700'}`}>
                        {thread.from}
                      </span>
                      <span className="whitespace-nowrap text-xs text-gray-500">{thread.date}</span>
                    </div>
                    <p className={`truncate text-sm ${thread.unread ? 'font-medium text-gray-900' : 'text-gray-700'}`}>
                      {thread.subject}
                    </p>
                    <p className="truncate text-xs text-gray-500">{thread.preview}</p>
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <Badge variant={tagVariant[thread.tag]} className="text-[10px] capitalize">
                        {thread.tag.replace('-', ' ')}
                      </Badge>
                      {thread.starred && <Star className="w-3.5 h-3.5 fill-yellow-400 text-yellow-400" />}
                      {thread.hasAttachment && <Paperclip className="w-3.5 h-3.5 text-gray-400" />}
                      {thread.unread && <span className="ml-auto h-2 w-2 rounded-full bg-primary" />}
                    </div>
                  </button>
                </li>
              ))}
              {filtered.length === 0 && (
                <li className="py-8 text-center text-sm text-gray-500">No messages found</li>
              )}
            </ul>
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardContent className="flex h-full flex-col p-6">
            <div className="flex items-start justify-between gap-4 border-b border-gray-100 pb-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">{selected.subject}</h2>
                <p className="text-sm text-gray-600">
                  From <span className="font-medium">{selected.from}</span> • {selected.date}
                </p>
              </div>
              <div className="flex gap-1">
                <Button variant="ghost" size="sm"><Star className="w-4 h-4" /></Button>
                <Button variant="ghost" size="sm"><Archive className="w-4 h-4" /></Button>
                <Button variant="ghost" size="sm" className="text-red-600"><Trash2 className="w-4 h-4" /></Button>
              </div>
            </div>
            <div className="flex-1 py-4 text-sm leading-relaxed text-gray-700">
              <p>{selected.preview}</p>
              <p className="mt-4">Best regards,</p>
              <p className="font-medium text-gray-900">{selected.from}</p>
            </div>
            <div className="border-t border-gray-100 pt-4">
              <textarea
                className="w-full rounded-md border border-gray-300 p-3 text-sm"
                rows={3}
                placeholder="Write a reply..."
              />
              <div className="mt-2 flex justify-end gap-2">
                <Button variant="outline">
                  <Reply className="w-4 h-4 mr-2" />
                  Reply
                </Button>
                <Button>
                  <Send className="w-4 h-4 mr-2" />
                  Send
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
