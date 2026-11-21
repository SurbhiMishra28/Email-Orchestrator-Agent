import React, { useState } from 'react';
import { TrendingUp, TrendingDown, Send, MailOpen, MousePointerClick, Reply, BarChart2 } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Badge, Select } from '@email-orchestrator/ui-components';

const kpis = [
  { label: 'Emails Sent', value: '18,420', change: '+12.4%', positive: true, icon: Send },
  { label: 'Open Rate', value: '42.5%', change: '+2.1%', positive: true, icon: MailOpen },
  { label: 'Click Rate', value: '7.3%', change: '-0.4%', positive: false, icon: MousePointerClick },
  { label: 'Reply Rate', value: '8.3%', change: '+1.2%', positive: true, icon: Reply },
];

const timeline = [
  { label: 'Sep', sent: 2100, opened: 880, clicked: 150, replied: 62 },
  { label: 'Oct', sent: 3400, opened: 1420, clicked: 240, replied: 98 },
  { label: 'Nov', sent: 4200, opened: 1810, clicked: 310, replied: 124 },
  { label: 'Dec', sent: 3900, opened: 1650, clicked: 280, replied: 110 },
  { label: 'Jan', sent: 4820, opened: 2050, clicked: 360, replied: 145 },
];

const topCampaigns = [
  { id: 1, name: 'Q4 Product Launch', sent: 1250, openRate: '42.6%', clickRate: '7.1%', replyRate: '1.8%' },
  { id: 2, name: 'Welcome Sequence', sent: 3421, openRate: '42.6%', clickRate: '6.8%', replyRate: '2.0%' },
  { id: 3, name: 'Weekly Newsletter #42', sent: 980, openRate: '38.2%', clickRate: '5.4%', replyRate: '0.9%' },
];

const maxSent = Math.max(...timeline.map(t => t.sent));

export function AnalyticsPage() {
  const [range, setRange] = useState('6m');

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
          <p className="text-gray-600">Performance across campaigns and channels</p>
        </div>
        <Select
          value={range}
          onChange={e => setRange(e.target.value)}
          options={[
            { value: '30d', label: 'Last 30 days' },
            { value: '3m', label: 'Last 3 months' },
            { value: '6m', label: 'Last 6 months' },
            { value: '12m', label: 'Last 12 months' },
          ]}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {kpis.map(kpi => (
          <Card key={kpi.label}>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">{kpi.label}</p>
                  <p className="mt-1 text-3xl font-bold text-gray-900">{kpi.value}</p>
                </div>
                <div className="p-3 bg-primary/10 rounded-lg">
                  <kpi.icon className="w-6 h-6 text-primary" />
                </div>
              </div>
              <div className="mt-4 flex items-center gap-1.5">
                {kpi.positive ? (
                  <TrendingUp className="w-4 h-4 text-green-600" />
                ) : (
                  <TrendingDown className="w-4 h-4 text-red-600" />
                )}
                <span className={kpi.positive ? 'text-sm font-medium text-green-600' : 'text-sm font-medium text-red-600'}>
                  {kpi.change}
                </span>
                <span className="text-sm text-gray-500">vs previous period</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <BarChart2 className="w-5 h-5 text-gray-400" />
            Volume Over Time
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-64 items-end gap-4">
            {timeline.map(point => (
              <div key={point.label} className="flex flex-1 flex-col items-center gap-2">
                <div className="flex w-full flex-1 items-end justify-center gap-1">
                  <div
                    className="w-3 rounded-t bg-primary/30"
                    style={{ height: `${(point.opened / maxSent) * 100}%` }}
                    title={`${point.opened} opened`}
                  />
                  <div
                    className="w-3 rounded-t bg-primary"
                    style={{ height: `${(point.sent / maxSent) * 100}%` }}
                    title={`${point.sent} sent`}
                  />
                </div>
                <span className="text-xs text-gray-500">{point.label}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 flex items-center gap-4 text-xs text-gray-600">
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded bg-primary" /> Sent</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded bg-primary/30" /> Opened</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Top Campaigns</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="p-4 text-left font-medium text-gray-600">Campaign</th>
                  <th className="p-4 text-right font-medium text-gray-600">Sent</th>
                  <th className="p-4 text-right font-medium text-gray-600">Open Rate</th>
                  <th className="p-4 text-right font-medium text-gray-600">Click Rate</th>
                  <th className="p-4 text-right font-medium text-gray-600">Reply Rate</th>
                </tr>
              </thead>
              <tbody>
                {topCampaigns.map(campaign => (
                  <tr key={campaign.id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                    <td className="p-4 font-medium text-gray-900">{campaign.name}</td>
                    <td className="p-4 text-right text-gray-700">{campaign.sent.toLocaleString()}</td>
                    <td className="p-4 text-right"><Badge variant="success">{campaign.openRate}</Badge></td>
                    <td className="p-4 text-right text-gray-700">{campaign.clickRate}</td>
                    <td className="p-4 text-right text-gray-700">{campaign.replyRate}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
