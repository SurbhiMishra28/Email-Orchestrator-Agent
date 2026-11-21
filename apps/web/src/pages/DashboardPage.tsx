import React from 'react';
import { Link } from 'react-router-dom';
import { Mail, Users, Send, TrendingUp, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Badge, Button } from '@email-orchestrator/ui-components';

const stats = [
  { name: 'Total Contacts', value: '12,345', change: '+12%', changeType: 'positive', icon: Users },
  { name: 'Campaigns Sent', value: '234', change: '+8%', changeType: 'positive', icon: Send },
  { name: 'Open Rate', value: '42.5%', change: '+2.1%', changeType: 'positive', icon: TrendingUp },
  { name: 'Reply Rate', value: '8.3%', change: '-0.5%', changeType: 'negative', icon: Mail },
];

const recentCampaigns = [
  { id: 1, name: 'Q4 Product Launch', status: 'sent', sent: '2 hours ago', delivered: 1250, opened: 532, clicked: 89 },
  { id: 2, name: 'Black Friday Sale', status: 'scheduled', sent: 'Tomorrow 10:00', delivered: 0, opened: 0, clicked: 0 },
  { id: 3, name: 'Weekly Newsletter #42', status: 'draft', sent: '—', delivered: 0, opened: 0, clicked: 0 },
  { id: 4, name: 'Welcome Sequence', status: 'active', sent: 'Ongoing', delivered: 3421, opened: 1456, clicked: 234 },
];

export function DashboardPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-gray-600">Overview of your email marketing performance</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to="/campaigns">Create Campaign</Link>
          </Button>
          <Button asChild>
            <Link to="/contacts">Import Contacts</Link>
          </Button>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <Card key={stat.name}>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">{stat.name}</p>
                  <p className="mt-1 text-3xl font-bold text-gray-900">{stat.value}</p>
                </div>
                <div className="p-3 bg-primary/10 rounded-lg">
                  <stat.icon className="w-6 h-6 text-primary" />
                </div>
              </div>
              <div className="mt-4 flex items-center gap-2">
                <span className={cn(
                  'text-sm font-medium',
                  stat.changeType === 'positive' ? 'text-green-600' : 'text-red-600'
                )}>
                  {stat.change}
                </span>
                <span className="text-sm text-gray-500">vs last month</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Recent Campaigns */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Recent Campaigns</CardTitle>
          <Button variant="ghost" asChild>
            <Link to="/campaigns">View all</Link>
          </Button>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left p-4 font-medium text-gray-600">Campaign</th>
                  <th className="text-left p-4 font-medium text-gray-600">Status</th>
                  <th className="text-left p-4 font-medium text-gray-600">Sent</th>
                  <th className="text-right p-4 font-medium text-gray-600">Delivered</th>
                  <th className="text-right p-4 font-medium text-gray-600">Opened</th>
                  <th className="text-right p-4 font-medium text-gray-600">Clicked</th>
                </tr>
              </thead>
              <tbody>
                {recentCampaigns.map((campaign) => (
                  <tr key={campaign.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="p-4">
                      <Link to={`/campaigns/${campaign.id}`} className="font-medium text-gray-900 hover:text-primary">
                        {campaign.name}
                      </Link>
                    </td>
                    <td className="p-4">
                      <Badge variant={getStatusVariant(campaign.status)}>
                        {campaign.status}
                      </Badge>
                    </td>
                    <td className="p-4 text-gray-600">{campaign.sent}</td>
                    <td className="p-4 text-right text-gray-900">{campaign.delivered.toLocaleString()}</td>
                    <td className="p-4 text-right text-gray-900">{campaign.opened.toLocaleString()}</td>
                    <td className="p-4 text-right text-gray-900">{campaign.clicked.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Quick Actions */}
      <div className="grid gap-4 md:grid-cols-3">
        <QuickActionCard
          title="Create Campaign"
          description="Start a new email campaign"
          icon={Send}
          href="/campaigns"
          primary
        />
        <QuickActionCard
          title="Import Contacts"
          description="Add new contacts via CSV"
          icon={Users}
          href="/contacts"
        />
        <QuickActionCard
          title="Write with AI"
          description="Generate email content"
          icon={Mail}
          href="/templates"
        />
      </div>
    </div>
  );
}

function getStatusVariant(status: string) {
  switch (status) {
    case 'sent': return 'success';
    case 'scheduled': return 'default';
    case 'draft': return 'secondary';
    case 'active': return 'default';
    default: return 'outline';
  }
}

function QuickActionCard({ title, description, icon: Icon, href, primary = false }: {
  title: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  href: string;
  primary?: boolean;
}) {
  return (
    <Link to={href} className="group">
      <Card className="h-full transition-shadow hover:shadow-lg cursor-pointer">
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <div className={cn(
              'p-3 rounded-lg flex-shrink-0',
              primary ? 'bg-primary text-primary-foreground' : 'bg-gray-100 text-gray-700'
            )}>
              <Icon className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 group-hover:text-primary transition-colors">{title}</h3>
              <p className="mt-1 text-sm text-gray-600">{description}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function cn(...classes: (string | undefined | null | false)[]) {
  return classes.filter(Boolean).join(' ');
}