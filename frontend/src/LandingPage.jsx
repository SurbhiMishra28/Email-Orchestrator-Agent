import { useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Brain,
  Check,
  CheckCircle,
  ChevronDown,
  Gauge,
  Globe,
  Layers,
  Mail,
  Menu,
  Play,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Star,
  Users,
  Workflow,
  X,
  Zap,
} from "lucide-react";

const NAV = [
  {
    label: "Platform",
    items: ["Email orchestration", "SMTP relay", "Automations", "Deliverability", "AI insights"],
  },
  {
    label: "Solutions",
    items: ["Small business", "Agencies", "Enterprise", "Developers"],
  },
  { label: "Pricing", href: "#pricing" },
  {
    label: "Resources",
    items: ["Docs", "API reference", "Deliverability guide", "Status"],
  },
];

const LOGOS = ["NORTHWIND", "Hopper", "BLETCHLEY", "Orbital", "KERNEL", "Naval", "ARC", "LUMEN"];

const CHANNELS = [
  {
    icon: Mail,
    title: "Email marketing",
    body: "Design, send and measure campaigns from one editor, with templates that already render.",
  },
  {
    icon: Send,
    title: "SMTP relay",
    body: "Send through your own providers or ours, with routing, pacing and failover built in.",
  },
  {
    icon: Workflow,
    title: "Automations",
    body: "Visual journeys with triggers, conditions, delays and AI decisions — no code.",
  },
  {
    icon: Gauge,
    title: "Deliverability",
    body: "Inbox placement, reputation and provider health, per campaign and per domain.",
  },
  {
    icon: Sparkles,
    title: "AI insights",
    body: "Recommendations that name the provider, the send time and the segment to move.",
  },
  {
    icon: Users,
    title: "Team & roles",
    body: "Workspaces, approvals and audit trails for teams that send under one brand.",
  },
];

const AGENTS = [
  {
    icon: Brain,
    name: "Marketing agent",
    body: "Drafts the campaign, segments the audience and picks the send window.",
    tag: "Composer",
  },
  {
    icon: Send,
    name: "Delivery agent",
    body: "Routes every send across the pool and reroutes when a provider degrades.",
    tag: "Sender",
  },
  {
    icon: RefreshCw,
    name: "Reply agent",
    body: "Classifies replies, answers the positive ones and books the meeting.",
    tag: "New",
  },
  {
    icon: BarChart3,
    name: "Analyst agent",
    body: "Turns delivery data into a decision you can act on the same day.",
    tag: "Insights",
  },
];

const SEGMENTS = [
  {
    id: "smb",
    label: "Small business",
    eyebrow: "FOR FOUNDERS & SMALL TEAMS",
    title: "Powerful tools, simple setup",
    body: "Start fast. Grow confidently. Launch polished campaigns without complexity.",
    points: [
      "Drag-and-drop campaign editor",
      "Ready-to-use templates",
      "No-code marketing automation",
      "Advanced segmentation",
    ],
    cta: "Explore for small business",
    stat: "25k",
    statLabel: "emails included on Starter",
  },
  {
    id: "agency",
    label: "Agencies",
    eyebrow: "FOR AGENCIES & CONSULTANCIES",
    title: "Every client, one control centre",
    body: "Run multiple brands and domains without mixing lists, senders or reports.",
    points: [
      "Unlimited providers per workspace",
      "Client-level roles and approvals",
      "White-label reporting",
      "Shared template library",
    ],
    cta: "Explore for agencies",
    stat: "3.4×",
    statLabel: "more campaigns shipped per week",
  },
  {
    id: "enterprise",
    label: "Enterprise",
    eyebrow: "FOR HIGH-VOLUME SENDERS",
    title: "Scale without the fire drills",
    body: "Dedicated infrastructure, an SLA and a named contact who knows your sending.",
    points: [
      "Dedicated IP pools",
      "99.99% uptime SLA",
      "SSO and audit logs",
      "Custom integrations",
    ],
    cta: "Talk to sales",
    stat: "99.99%",
    statLabel: "contractual uptime",
  },
];

const AWARDS = [
  "Capterra Ease of Use 2026",
  "G2 Leader — Email",
  "Software Advice Front Runner",
  "GetApp Category Leader",
  "TrustRadius Top Rated",
];

const STORIES = [
  {
    stat: "$1M",
    label: "revenue added in year one",
    quote:
      "We run four providers across three brands. MailMatrix is the first tool that made that boring instead of terrifying.",
    name: "Ada Lovelace",
    role: "Head of Growth, Northwind",
  },
  {
    stat: "47%",
    label: "more repeat replies",
    quote:
      "The reply handling alone paid for it. Positive replies get answered while we sleep, and nothing slips through.",
    name: "Grace Hopper",
    role: "CTO, Hopper Labs",
  },
  {
    stat: "40%",
    label: "revenue growth",
    quote:
      "Deliverability used to be a monthly fire drill. Now it is a number on a dashboard that I actually trust.",
    name: "Alan Turing",
    role: "Founder, Bletchley",
  },
];

const FOOTER = [
  {
    title: "Product",
    links: [
      "Email marketing",
      "Transactional email",
      "SMTP relay",
      "Automations",
      "Deliverability",
      "AI insights",
      "Pricing",
      "Integrations",
    ],
  },
  {
    title: "Compare",
    links: [
      "MailMatrix vs Brevo",
      "MailMatrix vs SendGrid",
      "MailMatrix vs Mailchimp",
      "MailMatrix vs Klaviyo",
      "Free SMTP server",
      "Reviews",
    ],
  },
  {
    title: "Resources",
    links: [
      "Help center",
      "Platform status",
      "Community",
      "Blog",
      "Email templates",
      "API docs",
      "Tools & calculators",
    ],
  },
  {
    title: "Company",
    links: ["About us", "Contact us", "Careers", "Press", "Partners", "Security", "GDPR"],
  },
];

function RotatingWord({ words }) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setIndex((value) => (value + 1) % words.length), 2200);
    return () => clearInterval(timer);
  }, [words.length]);

  return (
    <span className="bf-rotate">
      {words.map((word, i) => (
        <span
          key={word}
          className={"bf-rotate-word " + (i === index ? "bf-rotate-active" : "")}
          aria-hidden={i !== index}
        >
          {word}
        </span>
      ))}
    </span>
  );
}

function Stars() {
  return (
    <span className="flex gap-0.5 text-[#f5a623]">
      {Array.from({ length: 5 }).map((_, i) => (
        <Star key={i} className="h-3.5 w-3.5 fill-current" />
      ))}
    </span>
  );
}

function HeroVisual() {
  return (
    <div className="bf-window">
      <div className="bf-window-bar">
        <span className="h-2 w-2 rounded-full bg-[#ff5f57]" />
        <span className="h-2 w-2 rounded-full bg-[#febc2e]" />
        <span className="h-2 w-2 rounded-full bg-[#28c840]" />
        <span className="ml-2 truncate text-[10.5px] text-[#98a2b3]">
          app.mailmatrix.io / overview
        </span>
      </div>

      <div className="grid grid-cols-[44px_1fr]">
        <div className="flex flex-col items-center gap-3 border-r border-[#eaeced] bg-[#fafbfb] py-3">
          {[BarChart3, Send, Layers, Workflow, Sparkles, Users].map((Icon, i) => (
            <span
              key={i}
              className={
                "flex h-7 w-7 items-center justify-center rounded-lg " +
                (i === 0 ? "bg-[#0b9e6e] text-white" : "text-[#98a2b3]")
              }
            >
              <Icon className="h-3.5 w-3.5" />
            </span>
          ))}
        </div>

        <div className="min-w-0 p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-[11.5px] font-semibold text-[#101828]">
                Good morning, Surbhi
              </div>
              <div className="truncate text-[10px] text-[#98a2b3]">
                Here is what the fleet did overnight
              </div>
            </div>
            <span className="bf-live">
              <span className="h-1.5 w-1.5 rounded-full bg-[#0b9e6e]" />
              Live
            </span>
          </div>

          <div className="mt-2.5 grid grid-cols-4 gap-1.5">
            {[
              ["Sent", "284k"],
              ["Inbox", "99.2%"],
              ["Replies", "1,204"],
              ["AI score", "94"],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg border border-[#eaeced] bg-[#fafbfb] px-2 py-1.5">
                <div className="text-[8.5px] font-semibold uppercase tracking-[0.08em] text-[#98a2b3]">
                  {label}
                </div>
                <div className="text-[13px] font-semibold tabular-nums text-[#101828]">{value}</div>
              </div>
            ))}
          </div>

          <div className="mt-2 grid gap-2 sm:grid-cols-[1.4fr_1fr]">
            <div className="rounded-lg border border-[#eaeced] bg-[#fafbfb] p-2">
              <div className="flex items-center justify-between text-[9px] font-semibold uppercase tracking-[0.08em] text-[#98a2b3]">
                <span>Volume</span>
                <span className="text-[#0b9e6e]">+18%</span>
              </div>
              <svg viewBox="0 0 240 64" className="mt-1 h-14 w-full" preserveAspectRatio="none" aria-hidden="true">
                <path
                  d="M0 52 L28 44 L56 47 L84 30 L112 34 L140 20 L168 24 L196 12 L240 8 L240 64 L0 64 Z"
                  fill="#0b9e6e"
                  opacity="0.14"
                />
                <path
                  d="M0 52 L28 44 L56 47 L84 30 L112 34 L140 20 L168 24 L196 12 L240 8"
                  fill="none"
                  stroke="#0b9e6e"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>

            <div className="rounded-lg border border-[#eaeced] bg-[#fafbfb] p-2">
              <div className="mb-1.5 text-[9px] font-semibold uppercase tracking-[0.08em] text-[#98a2b3]">
                Provider health
              </div>
              {[
                ["Mailgun", 98, "bg-[#0b9e6e]"],
                ["SendGrid", 94, "bg-[#12a4c4]"],
                ["Amazon SES", 91, "bg-[#5ac8a0]"],
              ].map(([name, score, tone]) => (
                <div key={name} className="mb-1.5 flex items-center gap-1.5 last:mb-0">
                  <span className="w-[62px] shrink-0 truncate text-[9.5px] text-[#475467]">
                    {name}
                  </span>
                  <span className="h-1 flex-1 overflow-hidden rounded-full bg-[#eaeced]">
                    <span className={"block h-full rounded-full " + tone} style={{ width: score + "%" }} />
                  </span>
                  <span className="w-5 shrink-0 text-right text-[9px] tabular-nums text-[#667085]">
                    {score}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-2 rounded-lg border border-[#eaeced] bg-[#fafbfb] p-2">
            <div className="mb-1 flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-[0.1em] text-[#98a2b3]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#0b9e6e]" />
              Live agent activity
            </div>
            {[
              ["Composer", "drafted 12 intros"],
              ["Sender", "delivered via Mailgun"],
              ["Reply agent", "classified 3 replies"],
            ].map(([agent, detail]) => (
              <div key={agent} className="flex items-center gap-1.5 py-[3px] text-[9.5px]">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#0b9e6e]" />
                <span className="w-[64px] shrink-0 font-semibold text-[#344054]">{agent}</span>
                <span className="truncate text-[#667085]">{detail}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function CampaignTable() {
  const rows = [
    ["Q3 — Northwind outbound", "Sent", "284k", "99.2%"],
    ["Webinar follow-up", "Sent", "42k", "98.7%"],
    ["Trial nurture", "Scheduled", "18k", "—"],
    ["Win-back — APAC", "Draft", "—", "—"],
  ];
  return (
    <div className="bf-window">
      <div className="bf-window-bar">
        <span className="h-2 w-2 rounded-full bg-[#ff5f57]" />
        <span className="h-2 w-2 rounded-full bg-[#febc2e]" />
        <span className="h-2 w-2 rounded-full bg-[#28c840]" />
        <span className="ml-2 truncate text-[10.5px] text-[#98a2b3]">app.mailmatrix.io / campaigns</span>
      </div>
      <div className="p-3">
        <div className="flex items-center justify-between">
          <span className="text-[11.5px] font-semibold text-[#101828]">Campaigns</span>
          <span className="bf-btn bf-btn-sm">Create campaign</span>
        </div>
        <div className="mt-2.5 overflow-hidden rounded-lg border border-[#eaeced]">
          {rows.map(([name, status, volume, inbox], index) => (
            <div
              key={name}
              className={
                "grid grid-cols-[1.6fr_0.8fr_0.7fr_0.6fr] items-center gap-2 px-2.5 py-2 text-[10px] " +
                (index % 2 ? "bg-[#fafbfb]" : "bg-white")
              }
            >
              <span className="truncate font-medium text-[#344054]">{name}</span>
              <span className={"bf-status bf-status-" + status.toLowerCase()}>{status}</span>
              <span className="text-right tabular-nums text-[#667085]">{volume}</span>
              <span className="text-right tabular-nums text-[#667085]">{inbox}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ProviderPool() {
  const providers = [
    ["Mailgun", "Primary", 98, "42k"],
    ["SendGrid", "Failover", 94, "31k"],
    ["Amazon SES", "Bulk", 91, "18k"],
    ["Gmail API", "Transactional", 96, "12k"],
  ];
  return (
    <div className="bf-window">
      <div className="bf-window-bar">
        <span className="h-2 w-2 rounded-full bg-[#ff5f57]" />
        <span className="h-2 w-2 rounded-full bg-[#febc2e]" />
        <span className="h-2 w-2 rounded-full bg-[#28c840]" />
        <span className="ml-2 truncate text-[10.5px] text-[#98a2b3]">app.mailmatrix.io / providers</span>
      </div>
      <div className="grid gap-2 p-3 sm:grid-cols-2">
        {providers.map(([name, role, score, volume]) => (
          <div key={name} className="rounded-lg border border-[#eaeced] bg-[#fafbfb] p-2.5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-[#101828]">{name}</span>
              <span className="bf-live">{role}</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#eaeced]">
              <div className="h-full rounded-full bg-[#0b9e6e]" style={{ width: score + "%" }} />
            </div>
            <div className="mt-1.5 flex justify-between text-[9.5px] text-[#98a2b3]">
              <span>Health {score}</span>
              <span>{volume} today</span>
            </div>
          </div>
        ))}
      </div>
      <div className="mx-3 mb-3 flex items-center gap-2 rounded-lg border border-[#0b9e6e]/30 bg-[#0b9e6e]/10 px-2.5 py-2">
        <Zap className="h-3.5 w-3.5 shrink-0 text-[#0b9e6e]" />
        <span className="text-[10.5px] leading-snug text-[#344054]">
          Failover completed in <strong className="font-semibold">1.2s</strong> — 0 emails lost.
        </span>
      </div>
    </div>
  );
}

function AiInsights() {
  return (
    <div className="bf-window">
      <div className="bf-window-bar">
        <span className="h-2 w-2 rounded-full bg-[#ff5f57]" />
        <span className="h-2 w-2 rounded-full bg-[#febc2e]" />
        <span className="h-2 w-2 rounded-full bg-[#28c840]" />
        <span className="ml-2 truncate text-[10.5px] text-[#98a2b3]">app.mailmatrix.io / ai-insights</span>
      </div>
      <div className="space-y-2 p-3">
        {[
          ["Provider A is outperforming Provider B by 18%.", "Move 35% of volume to Mailgun."],
          ["Optimal send time detected: 9:00 AM.", "Expected reply lift +12%."],
          ["Campaign X is likely to achieve 27% higher engagement.", "Shift the remaining sends."],
        ].map(([title, detail]) => (
          <div key={title} className="rounded-lg border border-[#0b9e6e]/30 bg-[#0b9e6e]/10 px-2.5 py-2">
            <div className="flex items-start gap-1.5">
              <Sparkles className="mt-0.5 h-3 w-3 shrink-0 text-[#0b9e6e]" />
              <div className="min-w-0">
                <div className="text-[10.5px] font-medium leading-snug text-[#101828]">{title}</div>
                <div className="mt-0.5 text-[9.5px] text-[#667085]">{detail}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function LandingPage({ onSignIn, onDemo, onStart }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [openNav, setOpenNav] = useState(null);
  const [segment, setSegment] = useState("smb");

  const active = SEGMENTS.find((item) => item.id === segment) || SEGMENTS[0];

  return (
    <div className="bf-page">
      <div className="bf-announce">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-x-3 gap-y-1 px-5 py-2 text-[12px]">
          <span className="font-semibold text-white">Black Friday</span>
          <span className="text-white/80">
            30% off annual plans with the code <strong className="font-semibold text-white">MATRIX30</strong>
          </span>
          <span className="hidden text-white/60 sm:inline">· Ends in 02d 16h</span>
          <button onClick={onStart} className="font-semibold text-white underline underline-offset-2">
            Get the discount
          </button>
        </div>
      </div>

      <header className="bf-header">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-5">
          <button
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
            className="flex items-center gap-2"
            aria-label="MailMatrix home"
          >
            <span className="bf-mark">
              <Mail className="h-[18px] w-[18px]" />
            </span>
            <span className="text-[17px] font-bold tracking-[-0.02em] text-[#101828]">MailMatrix</span>
          </button>

          <nav className="hidden items-center gap-1 lg:flex">
            {NAV.map((item) =>
              item.href ? (
                <a
                  key={item.label}
                  href={item.href}
                  className="bf-nav-link"
                >
                  {item.label}
                </a>
              ) : (
                <div key={item.label} className="relative">
                  <button
                    onClick={() => setOpenNav(openNav === item.label ? null : item.label)}
                    className="bf-nav-link inline-flex items-center gap-1"
                    aria-expanded={openNav === item.label}
                  >
                    {item.label}
                    <ChevronDown className="h-3.5 w-3.5" />
                  </button>
                  {openNav === item.label && (
                    <div className="bf-menu">
                      {item.items.map((entry) => (
                        <a key={entry} href="#features" className="bf-menu-item">
                          {entry}
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              )
            )}
          </nav>

          <div className="flex items-center gap-2">
            <button onClick={onSignIn} className="bf-login max-sm:hidden">
              Log in
            </button>
            <button onClick={onStart} className="bf-btn bf-btn-sm">
              Sign up free
            </button>
            <button
              onClick={() => setMobileOpen((value) => !value)}
              className="bf-icon lg:hidden"
              aria-label="Toggle navigation"
              aria-expanded={mobileOpen}
            >
              {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>

        {mobileOpen && (
          <div className="border-t border-[#eaeced] bg-white px-5 py-3 lg:hidden">
            <div className="flex flex-col gap-1">
              {NAV.map((item) => (
                <a
                  key={item.label}
                  href={item.href || "#features"}
                  onClick={() => setMobileOpen(false)}
                  className="rounded-lg px-2 py-2 text-[14px] font-medium text-[#344054] hover:bg-[#f6f7f6]"
                >
                  {item.label}
                </a>
              ))}
              <button
                onClick={() => {
                  setMobileOpen(false);
                  onSignIn();
                }}
                className="bf-btn bf-btn-ghost mt-1"
              >
                Log in
              </button>
            </div>
          </div>
        )}
      </header>

      <section className="bf-hero">
        <div className="mx-auto max-w-4xl px-5 text-center">
          <h1 className="bf-h1">
            Turn every
            <br className="sm:hidden" />{" "}
            <RotatingWord words={["Email", "SMTP", "Campaign", "Reply"]} /> into a
            <br className="hidden sm:block" /> lifetime customer
          </h1>
          <p className="bf-sub">
            One AI-powered platform for all your sending. Orchestrate every provider, automate
            outreach and maximise inbox placement — from the first send to enterprise scale.
          </p>

          <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
            <button onClick={onStart} className="bf-btn">
              Sign up free
            </button>
            <button onClick={onDemo} className="bf-btn bf-btn-ghost">
              <Play className="h-4 w-4" />
              Get a demo
            </button>
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-[12.5px] text-[#667085]">
            <span className="flex items-center gap-1.5">
              <CheckCircle className="h-4 w-4 text-[#0b9e6e]" />
              No credit card required
            </span>
            <span className="flex items-center gap-1.5">
              <CheckCircle className="h-4 w-4 text-[#0b9e6e]" />
              Free demo workspace
            </span>
          </div>

          <div className="mt-7 flex flex-wrap items-center justify-center gap-2 text-[12.5px] text-[#667085]">
            <Stars />
            <span className="font-semibold text-[#101828]">4.8/5</span>
            <span>Loved by 12,000+ growth teams</span>
          </div>
        </div>

        <div className="mx-auto mt-12 max-w-5xl px-5">
          <HeroVisual />
        </div>
      </section>

      <section className="border-y border-[#eaeced] bg-white">
        <div className="mx-auto max-w-6xl px-5 py-9">
          <p className="text-center text-[11px] font-semibold uppercase tracking-[0.16em] text-[#98a2b3]">
            Join 12,000+ customers around the world who trust MailMatrix
          </p>
          <div className="mt-6 grid grid-cols-2 items-center gap-x-8 gap-y-5 sm:grid-cols-4 lg:grid-cols-8">
            {LOGOS.map((logo, index) => (
              <span
                key={logo}
                className={
                  "truncate text-center text-[13px] text-[#667085] " +
                  (index % 3 === 0
                    ? "font-bold uppercase tracking-[0.12em]"
                    : index % 3 === 1
                      ? "font-semibold tracking-tight"
                      : "font-medium uppercase tracking-[0.08em]")
                }
              >
                {logo}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section id="features" className="bf-section">
        <div className="mx-auto max-w-6xl px-5">
          <div className="bf-feature">
            <div className="bf-feature-copy">
              <div className="bf-eyebrow">Multichannel marketing &amp; automation</div>
              <h2 className="bf-h2">Grow your business easily</h2>
              <p className="bf-body">
                Launch campaigns in minutes and drive more revenue. Skip the learning curve with
                ready-made templates, guided automation and tools anyone can master.
              </p>
              <button onClick={onStart} className="bf-link">
                Learn more <ArrowRight className="h-4 w-4" />
              </button>
            </div>
            <div className="bf-feature-visual">
              <CampaignTable />
            </div>
          </div>

          <div className="bf-feature bf-feature-reverse">
            <div className="bf-feature-copy">
              <div className="bf-eyebrow">All-in-one solution</div>
              <h2 className="bf-h2">Built to scale with you</h2>
              <p className="bf-body">
                As you send more, add providers, brands and channels without adding tools. Manage
                the entire customer journey from one platform — for marketing, sales and lifecycle.
              </p>
              <button onClick={onStart} className="bf-link">
                Sign up free <ArrowRight className="h-4 w-4" />
              </button>
            </div>
            <div className="bf-feature-visual">
              <ProviderPool />
            </div>
          </div>

          <div className="bf-feature">
            <div className="bf-feature-copy">
              <div className="bf-eyebrow">AI-first platform</div>
              <h2 className="bf-h2">Accelerate with AI</h2>
              <p className="bf-body">
                Work smarter with an agent fleet that drafts, routes, classifies replies and
                recommends the next move — with every action written to the log.
              </p>
              <button onClick={onDemo} className="bf-link">
                See it in the demo <ArrowRight className="h-4 w-4" />
              </button>
            </div>
            <div className="bf-feature-visual">
              <AiInsights />
            </div>
          </div>
        </div>
      </section>

      <section className="bf-section bf-section-tint">
        <div className="mx-auto max-w-6xl px-5">
          <div className="max-w-2xl">
            <div className="bf-eyebrow">Everything in one place</div>
            <h2 className="bf-h2">Engage your audience your way</h2>
          </div>

          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {CHANNELS.map((channel) => (
              <article key={channel.title} className="bf-card">
                <span className="bf-card-icon">
                  <channel.icon className="h-5 w-5" />
                </span>
                <h3 className="mt-3 text-[15px] font-semibold text-[#101828]">{channel.title}</h3>
                <p className="mt-1.5 text-[13px] leading-relaxed text-[#667085]">{channel.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="bf-section">
        <div className="mx-auto max-w-6xl px-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="max-w-2xl">
              <div className="bf-eyebrow">Powered by MailMatrix AI</div>
              <h2 className="bf-h2">AI agents that work with you, and for you</h2>
              <p className="bf-body mt-3">
                Meet the fleet: always-on specialists that remove the busywork so your team can
                focus on strategy.
              </p>
            </div>
            <button onClick={onDemo} className="bf-btn bf-btn-ghost">
              Explore the demo
            </button>
          </div>

          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {AGENTS.map((agent) => (
              <article key={agent.name} className="bf-card bf-card-agent">
                <div className="flex items-center justify-between">
                  <span className="bf-card-icon">
                    <agent.icon className="h-5 w-5" />
                  </span>
                  <span className={"bf-tag " + (agent.tag === "New" ? "bf-tag-new" : "")}>
                    {agent.tag}
                  </span>
                </div>
                <h3 className="mt-3 text-[15px] font-semibold text-[#101828]">{agent.name}</h3>
                <p className="mt-1.5 text-[13px] leading-relaxed text-[#667085]">{agent.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="bf-section bf-section-tint">
        <div className="mx-auto max-w-6xl px-5">
          <div className="flex flex-wrap gap-1.5">
            {SEGMENTS.map((item) => (
              <button
                key={item.id}
                onClick={() => setSegment(item.id)}
                className={"bf-tab " + (segment === item.id ? "bf-tab-active" : "")}
              >
                {item.label}
              </button>
            ))}
          </div>

          <div className="mt-8 grid items-center gap-8 lg:grid-cols-2">
            <div>
              <div className="bf-eyebrow">{active.eyebrow}</div>
              <h2 className="bf-h2">{active.title}</h2>
              <p className="bf-body mt-3">{active.body}</p>

              <ul className="mt-5 space-y-2.5">
                {active.points.map((point) => (
                  <li key={point} className="flex items-start gap-2 text-[14px] text-[#344054]">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-[#0b9e6e]" />
                    {point}
                  </li>
                ))}
              </ul>

              <button onClick={onStart} className="bf-btn mt-6">
                {active.cta}
              </button>

              <div className="mt-7 flex items-end gap-2 border-t border-[#eaeced] pt-5">
                <span className="text-[30px] font-bold leading-none tracking-[-0.02em] text-[#101828]">
                  {active.stat}
                </span>
                <span className="pb-1 text-[12.5px] text-[#667085]">{active.statLabel}</span>
              </div>
            </div>

            <div className="bf-feature-visual">
              {segment === "smb" && <CampaignTable />}
              {segment === "agency" && <ProviderPool />}
              {segment === "enterprise" && <AiInsights />}
            </div>
          </div>
        </div>
      </section>

      <section className="border-y border-[#eaeced] bg-white">
        <div className="mx-auto max-w-6xl px-5 py-8">
          <p className="text-center text-[11px] font-semibold uppercase tracking-[0.16em] text-[#98a2b3]">
            Awarded for excellence
          </p>
          <div className="mt-5 flex flex-wrap items-center justify-center gap-x-8 gap-y-3">
            {AWARDS.map((award) => (
              <span key={award} className="text-[12px] font-medium text-[#475467]">
                {award}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section className="bf-section">
        <div className="mx-auto max-w-6xl px-5">
          <div className="max-w-2xl">
            <div className="bf-eyebrow">Customer stories</div>
            <h2 className="bf-h2">Real stories, real success</h2>
          </div>

          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {STORIES.map((story) => (
              <figure key={story.name} className="bf-card flex h-full flex-col">
                <div className="text-[26px] font-bold leading-none tracking-[-0.02em] text-[#0b9e6e]">
                  {story.stat}
                </div>
                <div className="mt-1 text-[12px] text-[#667085]">{story.label}</div>
                <blockquote className="mt-4 flex-1 text-[13.5px] leading-relaxed text-[#344054]">
                  “{story.quote}”
                </blockquote>
                <figcaption className="mt-4 border-t border-[#eaeced] pt-3">
                  <div className="text-[12.5px] font-semibold text-[#101828]">{story.name}</div>
                  <div className="text-[11.5px] text-[#667085]">{story.role}</div>
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-[#0b9e6e]">
        <div className="mx-auto max-w-4xl px-5 py-14 text-center">
          <h2 className="text-[30px] font-bold leading-tight tracking-[-0.02em] text-white sm:text-[36px]">
            Ready to grow with MailMatrix?
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-[15px] leading-relaxed text-white/80">
            Connect with customers, convert more leads and drive repeat business — all from one
            platform.
          </p>
          <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
            <button
              onClick={onStart}
              className="bf-btn bf-btn-white"
            >
              Sign up free
            </button>
            <button
              onClick={onDemo}
              className="bf-btn bf-btn-outline-white"
            >
              Get a demo
            </button>
          </div>
          <p className="mt-4 text-[12px] text-white/75">No credit card required.</p>
        </div>
      </section>

      <footer className="border-t border-[#eaeced] bg-white">
        <div className="mx-auto max-w-6xl px-5 py-12">
          <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-[1.3fr_repeat(4,1fr)]">
            <div>
              <div className="flex items-center gap-2">
                <span className="bf-mark">
                  <Mail className="h-[18px] w-[18px]" />
                </span>
                <span className="text-[16px] font-bold tracking-[-0.02em] text-[#101828]">
                  MailMatrix
                </span>
              </div>
              <p className="mt-3 max-w-xs text-[12.5px] leading-relaxed text-[#667085]">
                Intelligent email orchestration at scale. Every provider, campaign and reply in one
                queue.
              </p>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {["SOC 2", "GDPR", "99.99%"].map((item) => (
                  <span key={item} className="bf-tag">
                    {item}
                  </span>
                ))}
              </div>
              <div className="mt-4 flex items-center gap-1.5 text-[12px] text-[#667085]">
                <Globe className="h-3.5 w-3.5" />
                Global infrastructure
              </div>
            </div>

            {FOOTER.map((column) => (
              <div key={column.title}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#98a2b3]">
                  {column.title}
                </div>
                <ul className="mt-3 space-y-2">
                  {column.links.map((link) => (
                    <li key={link}>
                      <a
                        href="#features"
                        className="text-[12.5px] text-[#475467] transition-colors hover:text-[#0b9e6e]"
                      >
                        {link}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="mt-10 flex flex-col gap-3 border-t border-[#eaeced] pt-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-[11.5px] text-[#98a2b3]">
              © {new Date().getFullYear()} MailMatrix. All rights reserved.
            </p>
            <div className="flex flex-wrap items-center gap-4 text-[11.5px] text-[#667085]">
              <button onClick={onSignIn} className="hover:text-[#0b9e6e]">
                Log in
              </button>
              <button onClick={onDemo} className="hover:text-[#0b9e6e]">
                Demo
              </button>
              <a href="#pricing" className="hover:text-[#0b9e6e]">
                Pricing
              </a>
              <span>Privacy</span>
              <span>Terms</span>
              <span>Status</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}