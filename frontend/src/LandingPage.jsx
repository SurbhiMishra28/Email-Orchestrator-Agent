import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Brain,
  Check,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  CircleDot,
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
  { label: "Product", href: "#product" },
  { label: "Features", href: "#features" },
  { label: "How it works", href: "#how" },
  { label: "Pricing", href: "#pricing" },
  { label: "FAQ", href: "#faq" },
];

const LOGOS = [
  "NORTHWIND",
  "Hopper",
  "BLETCHLEY",
  "Orbital",
  "KERNEL",
  "Naval Systems",
];

const HIGHLIGHTS = [
  "SOC 2 compliant",
  "GDPR ready",
  "99.99% uptime",
  "Global infrastructure",
  "Enterprise security",
];

const FEATURES = [
  {
    icon: Brain,
    title: "AI email routing",
    body: "Every send is scored across your provider pool and routed to the one most likely to land in the inbox right now.",
    span: "lg:col-span-3",
    visual: "routing",
  },
  {
    icon: RefreshCw,
    title: "Smart failover",
    body: "A provider degrades, the queue reroutes in under two seconds. No stuck campaigns, no 3 a.m. pages.",
    span: "lg:col-span-3",
    visual: "failover",
  },
  {
    icon: Gauge,
    title: "Deliverability intelligence",
    body: "Inbox placement, bounce reasons and domain reputation, per provider and per campaign.",
    span: "lg:col-span-2",
    visual: "gauge",
  },
  {
    icon: Layers,
    title: "Multi-provider control",
    body: "SMTP, Gmail API and Resend pools in one control centre with real health scores.",
    span: "lg:col-span-2",
    visual: "providers",
  },
  {
    icon: Workflow,
    title: "Campaign automation",
    body: "A visual builder for triggers, conditions, delays and AI decisions — no glue scripts.",
    span: "lg:col-span-2",
    visual: "flow",
  },
];

const FLOW = [
  { icon: Mail, label: "Campaign", detail: "Brief & audience" },
  { icon: Workflow, label: "Routing engine", detail: "Score every provider" },
  { icon: Layers, label: "SMTP pool", detail: "Paced, capped" },
  { icon: ShieldCheck, label: "Provider pick", detail: "Best inbox odds" },
  { icon: Activity, label: "Delivery monitor", detail: "Live signals" },
  { icon: BarChart3, label: "Analytics & AI", detail: "Learns & adapts" },
];

const METRICS = [
  { value: 99.2, suffix: "%", decimals: 1, label: "Median inbox placement" },
  { value: 18, suffix: "%", decimals: 0, label: "Lift from AI routing" },
  { value: 6.4, suffix: "M", decimals: 1, label: "Emails orchestrated weekly" },
  { value: 1.2, suffix: "s", decimals: 1, label: "Average failover time" },
];

const TESTIMONIALS = [
  {
    quote:
      "We run four providers across three brands. MailMatrix is the first tool that made that boring instead of terrifying.",
    name: "Ada Lovelace",
    role: "Head of Growth, Northwind",
    initials: "AL",
    stat: "3 brands, one queue",
  },
  {
    quote:
      "The reply handling alone paid for it. Positive replies get answered while we sleep, and nothing slips through.",
    name: "Grace Hopper",
    role: "CTO, Hopper Labs",
    initials: "GH",
    stat: "41% more replies",
  },
  {
    quote:
      "Deliverability used to be a monthly fire drill. Now it is a number on a dashboard that I actually trust.",
    name: "Alan Turing",
    role: "Founder, Bletchley",
    initials: "AT",
    stat: "99.2% inbox rate",
  },
];

const PLANS = [
  {
    name: "Starter",
    monthly: 29,
    annual: 23,
    tagline: "For a first list and a first pipeline.",
    features: ["5 SMTP providers", "25k emails / month", "Basic analytics", "Email support"],
    cta: "Start free trial",
  },
  {
    name: "Professional",
    monthly: 99,
    annual: 79,
    tagline: "For teams sending every week.",
    features: [
      "25 SMTP providers",
      "250k emails / month",
      "AI routing",
      "Advanced analytics",
      "API access",
    ],
    cta: "Start free trial",
    featured: true,
  },
  {
    name: "Business",
    monthly: 299,
    annual: 239,
    tagline: "For multi-brand outbound operations.",
    features: [
      "Unlimited providers",
      "Unlimited sending",
      "Team access",
      "AI optimisation",
      "Priority support",
    ],
    cta: "Start free trial",
  },
  {
    name: "Enterprise",
    monthly: null,
    annual: null,
    tagline: "For regulated and high-volume senders.",
    features: [
      "Dedicated infrastructure",
      "99.99% SLA",
      "White label",
      "Custom integrations",
      "Account manager",
    ],
    cta: "Book a demo",
  },
];

const FAQS = [
  {
    q: "How is this different from Brevo or SendGrid?",
    a: "Those are sending tools. MailMatrix is the layer above them: it keeps your existing providers, scores every send across the pool, and reroutes when one degrades — then handles replies and follow-ups for you.",
  },
  {
    q: "Can I bring my own SMTP providers?",
    a: "Yes. Add SMTP, Gmail API or Resend credentials and they join the pool immediately. Nothing is locked to a single vendor, and you can cap or weight each provider.",
  },
  {
    q: "What happens when a provider goes down?",
    a: "The routing engine stops weighting it within seconds and drains the queue through the next-best provider. Sends already in flight are reported, not silently dropped.",
  },
  {
    q: "Does the AI actually send email on its own?",
    a: "Only if you let it. Autopilot is off by default; you approve the workflow, the caps and the templates, and every action is written to the activity log.",
  },
  {
    q: "Is the demo workspace safe to click around in?",
    a: "It is a real, isolated tenant with seeded data and no sending credentials, so nothing it does can reach a real mailbox or another workspace.",
  },
];

const SHOWCASE = [
  { id: "overview", label: "Overview", icon: BarChart3 },
  { id: "providers", label: "Providers", icon: Layers },
  { id: "automations", label: "Automations", icon: Workflow },
  { id: "insights", label: "AI insights", icon: Sparkles },
];

function useCountUp(target, decimals) {
  const ref = useRef(null);
  const [value, setValue] = useState(0);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;

    let frame = 0;
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries[0].isIntersecting) return;
        observer.disconnect();
        const start = performance.now();
        const duration = 1100;
        const tick = (now) => {
          const progress = Math.min(1, (now - start) / duration);
          const eased = 1 - Math.pow(1 - progress, 3);
          setValue(Number((target * eased).toFixed(decimals)));
          if (progress < 1) frame = requestAnimationFrame(tick);
        };
        frame = requestAnimationFrame(tick);
      },
      { threshold: 0.4 }
    );

    observer.observe(node);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [target, decimals]);

  return [ref, value];
}

function Metric({ value, suffix, decimals, label }) {
  const [ref, current] = useCountUp(value, decimals);
  return (
    <div ref={ref} className="surface p-5">
      <div className="text-[26px] font-semibold leading-none tracking-[-0.02em] text-ink-900">
        {current.toFixed(decimals)}
        {suffix}
      </div>
      <div className="mt-2 text-[12px] leading-snug text-ink-500">{label}</div>
    </div>
  );
}

function WindowBar({ url = "app.mailmatrix.io / overview" }) {
  return (
    <div className="lp-window-bar">
      <span className="h-2 w-2 rounded-full bg-danger-400" />
      <span className="h-2 w-2 rounded-full bg-warn-400" />
      <span className="h-2 w-2 rounded-full bg-brand-400" />
      <span className="ml-2 truncate text-[10.5px] text-ink-400">{url}</span>
    </div>
  );
}

function MiniChart({ tone = "brand" }) {
  const stroke = tone === "brand" ? "rgb(var(--brand-500))" : "rgb(var(--info-500))";
  return (
    <svg viewBox="0 0 240 64" className="h-16 w-full" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id={`fill-${tone}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        d="M0 52 L28 44 L56 47 L84 30 L112 34 L140 20 L168 24 L196 12 L240 8 L240 64 L0 64 Z"
        fill={`url(#fill-${tone})`}
      />
      <path
        d="M0 52 L28 44 L56 47 L84 30 L112 34 L140 20 L168 24 L196 12 L240 8"
        fill="none"
        stroke={stroke}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function HeroConsole() {
  const providers = [
    { name: "Mailgun", score: 98, volume: "42k", tone: "bg-brand-500" },
    { name: "SendGrid", score: 94, volume: "31k", tone: "bg-info-500" },
    { name: "Amazon SES", score: 91, volume: "18k", tone: "bg-brand-400" },
    { name: "Gmail API", score: 96, volume: "12k", tone: "bg-brand-600" },
  ];

  return (
    <div className="relative">
      <div className="lp-glow" aria-hidden="true" />

      <div className="lp-window">
        <WindowBar />

        <div className="grid grid-cols-[46px_1fr]">
          <div className="flex flex-col items-center gap-3 border-r border-ink-200 bg-ink-100/60 py-3">
            {[BarChart3, Send, Layers, Workflow, Sparkles, Users].map((Icon, index) => (
              <span
                key={index}
                className={
                  "flex h-7 w-7 items-center justify-center rounded-lg " +
                  (index === 0 ? "bg-brand-500 text-white" : "text-ink-400")
                }
              >
                <Icon className="h-3.5 w-3.5" />
              </span>
            ))}
          </div>

          <div className="min-w-0 p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-[11.5px] font-semibold text-ink-800">
                  Good morning, Surbhi
                </div>
                <div className="truncate text-[10px] text-ink-400">
                  Here is what the fleet did overnight
                </div>
              </div>
              <span className="chip shrink-0 border-brand-300/50 bg-brand-500/10 text-brand-700">
                <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
                Live
              </span>
            </div>

            <div className="mt-2.5 grid grid-cols-4 gap-1.5">
              {[
                { label: "Sent", value: "284k" },
                { label: "Inbox", value: "99.2%" },
                { label: "Replies", value: "1,204" },
                { label: "AI score", value: "94" },
              ].map((tile) => (
                <div key={tile.label} className="rounded-lg border border-ink-200 bg-ink-50 px-2 py-1.5">
                  <div className="text-[8.5px] font-semibold uppercase tracking-[0.08em] text-ink-400">
                    {tile.label}
                  </div>
                  <div className="text-[13px] font-semibold tabular-nums text-ink-900">{tile.value}</div>
                </div>
              ))}
            </div>

            <div className="mt-2 grid gap-2 sm:grid-cols-[1.4fr_1fr]">
              <div className="rounded-lg border border-ink-200 bg-ink-50 p-2">
                <div className="flex items-center justify-between text-[9px] font-semibold uppercase tracking-[0.08em] text-ink-400">
                  <span>Volume</span>
                  <span className="text-brand-600">+18%</span>
                </div>
                <MiniChart />
              </div>

              <div className="rounded-lg border border-ink-200 bg-ink-50 p-2">
                <div className="mb-1.5 text-[9px] font-semibold uppercase tracking-[0.08em] text-ink-400">
                  Provider health
                </div>
                <div className="space-y-1.5">
                  {providers.slice(0, 3).map((provider) => (
                    <div key={provider.name} className="flex items-center gap-1.5">
                      <span className="w-[62px] shrink-0 truncate text-[9.5px] text-ink-600">
                        {provider.name}
                      </span>
                      <span className="h-1 flex-1 overflow-hidden rounded-full bg-ink-200">
                        <span
                          className={"block h-full rounded-full " + provider.tone}
                          style={{ width: provider.score + "%" }}
                        />
                      </span>
                      <span className="w-5 shrink-0 text-right text-[9px] tabular-nums text-ink-500">
                        {provider.score}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-2 rounded-lg border border-ink-200 bg-ink-50 p-2">
              <div className="mb-1 flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-[0.1em] text-ink-400">
                <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
                Live agent activity
              </div>
              {[
                ["Composer", "drafted 12 intros", "ok"],
                ["Sender", "delivered via Mailgun", "ok"],
                ["Reply analyst", "classified 3 replies", "info"],
              ].map(([agent, detail, tone]) => (
                <div key={agent} className="flex items-center gap-1.5 py-[3px] text-[9.5px]">
                  <span
                    className={
                      "h-1.5 w-1.5 shrink-0 rounded-full " +
                      (tone === "ok" ? "bg-brand-500" : "bg-info-500")
                    }
                  />
                  <span className="w-[64px] shrink-0 font-semibold text-ink-700">{agent}</span>
                  <span className="truncate text-ink-500">{detail}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="lp-float lp-float-a">
        <Zap className="h-3.5 w-3.5 text-brand-600" />
        AI routing active
      </div>
      <div className="lp-float lp-float-b">
        <ShieldCheck className="h-3.5 w-3.5 text-brand-600" />
        99.99% uptime
      </div>
    </div>
  );
}

function FeatureVisual({ kind }) {
  if (kind === "routing") {
    return (
      <div className="mt-4 space-y-2">
        {[
          ["Mailgun", 96, "bg-brand-500"],
          ["SendGrid", 88, "bg-info-500"],
          ["Amazon SES", 74, "bg-brand-300"],
        ].map(([name, score, tone]) => (
          <div key={name} className="flex items-center gap-2">
            <span className="w-[74px] shrink-0 truncate text-[11px] text-ink-500">{name}</span>
            <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-200">
              <span className={"block h-full rounded-full " + tone} style={{ width: score + "%" }} />
            </span>
            <span className="w-6 shrink-0 text-right text-[10.5px] tabular-nums text-ink-500">
              {score}
            </span>
          </div>
        ))}
      </div>
    );
  }

  if (kind === "failover") {
    return (
      <div className="mt-4 flex items-center gap-2 rounded-lg border border-ink-200 bg-ink-50 px-2.5 py-2">
        <span className="flex items-center gap-1.5 text-[11px] font-medium text-ink-600">
          <span className="h-1.5 w-1.5 rounded-full bg-danger-500" />
          Mailgun
        </span>
        <ArrowRight className="h-3.5 w-3.5 text-ink-300" />
        <span className="flex items-center gap-1.5 text-[11px] font-medium text-ink-800">
          <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
          SendGrid
        </span>
        <span className="ml-auto rounded-md bg-brand-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-brand-700">
          1.2s
        </span>
      </div>
    );
  }

  if (kind === "gauge") {
    return (
      <div className="mt-4 flex items-center gap-3">
        <div className="relative h-16 w-16 shrink-0">
          <svg viewBox="0 0 36 36" className="h-16 w-16 -rotate-90">
            <circle cx="18" cy="18" r="15" fill="none" stroke="rgb(var(--ink-200))" strokeWidth="3" />
            <circle
              cx="18"
              cy="18"
              r="15"
              fill="none"
              stroke="rgb(var(--brand-500))"
              strokeWidth="3"
              strokeLinecap="round"
              strokeDasharray="94 95"
            />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-[13px] font-semibold text-ink-900">
            99%
          </span>
        </div>
        <div className="min-w-0 text-[11px] leading-relaxed text-ink-500">
          Inbox placement, bounce reasons and reputation — per provider.
        </div>
      </div>
    );
  }

  if (kind === "providers") {
    return (
      <div className="mt-4 flex flex-wrap gap-1.5">
        {["SMTP", "Gmail API", "Resend", "Mailgun", "SES"].map((name) => (
          <span key={name} className="chip">
            {name}
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className="mt-4 flex items-center gap-1.5">
      {[CircleDot, ChevronRight, CircleDot, ChevronRight, Sparkles].map((Icon, index) => (
        <Icon
          key={index}
          className={"h-3.5 w-3.5 " + (index === 4 ? "text-brand-600" : "text-ink-300")}
        />
      ))}
    </div>
  );
}

function ShowcasePanel({ tab }) {
  if (tab === "providers") {
    return (
      <div className="grid gap-2 sm:grid-cols-2">
        {[
          ["Mailgun", 98, "Healthy", "42k today"],
          ["SendGrid", 94, "Healthy", "31k today"],
          ["Amazon SES", 91, "Watch", "18k today"],
          ["Gmail API", 96, "Healthy", "12k today"],
        ].map(([name, score, status, volume]) => (
          <div key={name} className="rounded-lg border border-ink-200 bg-ink-50 p-2.5">
            <div className="flex items-center justify-between">
              <span className="text-[11.5px] font-semibold text-ink-800">{name}</span>
              <span className="badge badge-sent">{status}</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink-200">
              <div className="h-full rounded-full bg-brand-500" style={{ width: score + "%" }} />
            </div>
            <div className="mt-1.5 flex justify-between text-[10px] text-ink-400">
              <span>Health {score}</span>
              <span>{volume}</span>
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (tab === "automations") {
    return (
      <div className="space-y-2">
        {[
          ["Trigger", "Reply classified as positive", "brand"],
          ["Condition", "No meeting booked yet", "info"],
          ["AI decision", "Propose two time slots", "brand"],
          ["Action", "Send calendar link", "info"],
        ].map(([label, detail, tone]) => (
          <div
            key={label}
            className="flex items-center gap-2 rounded-lg border border-ink-200 bg-ink-50 px-2.5 py-2"
          >
            <span
              className={
                "h-1.5 w-1.5 shrink-0 rounded-full " +
                (tone === "brand" ? "bg-brand-500" : "bg-info-500")
              }
            />
            <span className="w-[74px] shrink-0 text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-400">
              {label}
            </span>
            <span className="truncate text-[11px] text-ink-600">{detail}</span>
          </div>
        ))}
      </div>
    );
  }

  if (tab === "insights") {
    return (
      <div className="space-y-2">
        {[
          ["Provider A is outperforming Provider B by 18%.", "Move 35% of volume to Mailgun."],
          ["Optimal send time detected: 9:00 AM.", "Expected reply lift +12%."],
          ["Campaign X is likely to achieve 27% higher engagement.", "Shift the remaining sends."],
        ].map(([title, detail]) => (
          <div key={title} className="rounded-lg border border-brand-300/40 bg-brand-500/5 px-2.5 py-2">
            <div className="flex items-start gap-1.5">
              <Sparkles className="mt-0.5 h-3 w-3 shrink-0 text-brand-600" />
              <div className="min-w-0">
                <div className="text-[11px] font-medium leading-snug text-ink-800">{title}</div>
                <div className="mt-0.5 text-[10px] text-ink-500">{detail}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div>
      <div className="grid grid-cols-4 gap-1.5">
        {[
          ["Sent", "284k"],
          ["Inbox", "99.2%"],
          ["Replies", "1,204"],
          ["AI score", "94"],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg border border-ink-200 bg-ink-50 px-2 py-1.5">
            <div className="text-[8.5px] font-semibold uppercase tracking-[0.08em] text-ink-400">
              {label}
            </div>
            <div className="text-[13px] font-semibold tabular-nums text-ink-900">{value}</div>
          </div>
        ))}
      </div>
      <div className="mt-2 rounded-lg border border-ink-200 bg-ink-50 p-2">
        <div className="flex items-center justify-between text-[9px] font-semibold uppercase tracking-[0.08em] text-ink-400">
          <span>Sending volume</span>
          <span className="text-brand-600">+18% vs last week</span>
        </div>
        <MiniChart />
      </div>
    </div>
  );
}

export default function LandingPage({ onSignIn, onDemo, onStart }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [annual, setAnnual] = useState(true);
  const [tab, setTab] = useState("overview");
  const [faqOpen, setFaqOpen] = useState(0);

  return (
    <div className="min-h-screen bg-ink-50">
      <header className="sticky top-0 z-40 border-b border-ink-200 bg-ink-50/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-5">
          <button
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
            className="flex items-center gap-2.5"
            aria-label="MailMatrix home"
          >
            <span className="brand-mark">
              <Mail className="h-[18px] w-[18px]" />
            </span>
            <span className="text-[15px] font-bold tracking-tight text-ink-900">MailMatrix</span>
          </button>

          <nav className="hidden items-center gap-6 lg:flex">
            {NAV.map((item) => (
              <a
                key={item.label}
                href={item.href}
                className="text-[13px] font-medium text-ink-500 transition-colors hover:text-ink-900"
              >
                {item.label}
              </a>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <button onClick={onSignIn} className="btn-ghost btn-sm max-sm:hidden">
              Sign in
            </button>
            <button onClick={onStart} className="btn-primary btn-sm">
              Start free trial
            </button>
            <button
              onClick={() => setMobileOpen((value) => !value)}
              className="icon-btn lg:hidden"
              aria-label="Toggle navigation"
              aria-expanded={mobileOpen}
            >
              {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>

        {mobileOpen && (
          <div className="border-t border-ink-200 bg-ink-50 px-5 py-3 lg:hidden">
            <div className="flex flex-col gap-1">
              {NAV.map((item) => (
                <a
                  key={item.label}
                  href={item.href}
                  onClick={() => setMobileOpen(false)}
                  className="rounded-lg px-2 py-2 text-[13px] font-medium text-ink-600 hover:bg-ink-100"
                >
                  {item.label}
                </a>
              ))}
              <button
                onClick={() => {
                  setMobileOpen(false);
                  onSignIn();
                }}
                className="btn-ghost btn-sm mt-1"
              >
                Sign in
              </button>
            </div>
          </div>
        )}
      </header>

      <section className="relative overflow-hidden">
        <div className="lp-mesh" aria-hidden="true" />
        <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-5 pb-16 pt-14 lg:grid-cols-[1.02fr_1fr] lg:pb-24 lg:pt-20">
          <div className="animate-fade-in">
            <span className="chip border-brand-300/50 bg-brand-500/10 text-brand-700">
              <Sparkles className="h-3 w-3" />
              Intelligent email orchestration
            </span>

            <h1 className="mt-5 text-[36px] font-semibold leading-[1.06] tracking-[-0.04em] text-ink-900 sm:text-[50px]">
              Orchestrate email
              <br className="hidden sm:block" />
              campaigns{" "}
              <span className="lp-gradient-text">at scale</span>
            </h1>

            <p className="mt-5 max-w-xl text-[15.5px] leading-relaxed text-ink-500">
              Manage multiple SMTP providers, automate outreach workflows, monitor deliverability and
              maximise inbox placement from one intelligent platform.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              <button onClick={onStart} className="btn-primary">
                Start free trial
                <ArrowRight className="h-4 w-4" />
              </button>
              <button onClick={onDemo} className="btn-ghost">
                <Play className="h-4 w-4" />
                Book a demo
              </button>
            </div>

            <div className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-2 text-[12px] text-ink-500">
              {["No credit card", "Live demo workspace", "Cancel anytime"].map((item) => (
                <span key={item} className="flex items-center gap-1.5">
                  <CheckCircle className="h-3.5 w-3.5 text-brand-600" />
                  {item}
                </span>
              ))}
            </div>

            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-ink-200 pt-5">
              {HIGHLIGHTS.map((item) => (
                <span key={item} className="flex items-center gap-1.5 text-[11px] text-ink-500">
                  <ShieldCheck className="h-3.5 w-3.5 text-brand-600" />
                  {item}
                </span>
              ))}
            </div>
          </div>

          <HeroConsole />
        </div>
      </section>

      <section className="border-y border-ink-200 bg-ink-100/60">
        <div className="mx-auto max-w-6xl px-5 py-8">
          <p className="text-center text-[10.5px] font-semibold uppercase tracking-[0.18em] text-ink-400">
            Trusted by modern growth teams
          </p>
          <div className="mt-5 grid grid-cols-2 items-center gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-6">
            {LOGOS.map((logo, index) => (
              <span
                key={logo}
                className={
                  "truncate text-center text-[13px] text-ink-400 " +
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

      <section id="product" className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
        <div className="max-w-2xl">
          <div className="breadcrumb">Platform</div>
          <h2 className="mt-1 text-[28px] font-semibold tracking-[-0.03em] text-ink-900 sm:text-[32px]">
            One control centre for every send
          </h2>
          <p className="mt-3 text-[14.5px] leading-relaxed text-ink-500">
            Providers, campaigns, replies and deliverability used to live in four tools. They now
            live in one queue with an agent fleet behind it.
          </p>
        </div>

        <div className="mt-10 grid gap-4 lg:grid-cols-6">
          {FEATURES.map((feature) => (
            <article
              key={feature.title}
              className={"surface lp-bento p-5 " + feature.span}
            >
              <span className="stat-icon bg-brand-50 text-brand-600">
                <feature.icon className="h-4 w-4" />
              </span>
              <h3 className="mt-3 text-[14.5px] font-semibold text-ink-900">{feature.title}</h3>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-500">{feature.body}</p>
              <FeatureVisual kind={feature.visual} />
            </article>
          ))}

          <article className="surface lp-bento flex flex-col justify-between p-5 lg:col-span-2">
            <div>
              <span className="stat-icon bg-brand-50 text-brand-600">
                <Sparkles className="h-4 w-4" />
              </span>
              <h3 className="mt-3 text-[14.5px] font-semibold text-ink-900">AI send optimisation</h3>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-500">
                Send-time and subject experiments that learn from your replies, not from generic
                benchmarks.
              </p>
            </div>
            <div className="mt-4 flex items-center gap-2 rounded-lg border border-brand-300/40 bg-brand-500/5 px-2.5 py-2">
              <Sparkles className="h-3.5 w-3.5 shrink-0 text-brand-600" />
              <span className="text-[11px] leading-snug text-ink-700">
                Optimal send time detected: <strong className="font-semibold">9:00 AM</strong>
              </span>
            </div>
          </article>
        </div>
      </section>

      <section className="border-y border-ink-200 bg-ink-100/50">
        <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="max-w-xl">
              <div className="breadcrumb">How it works</div>
              <h2 className="mt-1 text-[28px] font-semibold tracking-[-0.03em] text-ink-900 sm:text-[32px]">
                From campaign to inbox, in one pass
              </h2>
            </div>
            <span className="chip">
              <Activity className="h-3 w-3" />
              Live routing
            </span>
          </div>

          <div className="mt-9 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-6">
            {FLOW.map((step, index) => (
              <div key={step.label} className="relative">
                <div className="h-full rounded-xl border border-ink-200 bg-card p-3.5">
                  <span className="flex h-8 w-8 items-center justify-center rounded-[10px] border border-brand-300/40 bg-brand-500/10 text-brand-700">
                    <step.icon className="h-4 w-4" />
                  </span>
                  <div className="mt-2.5 text-[12.5px] font-semibold text-ink-800">{step.label}</div>
                  <div className="mt-0.5 text-[11px] leading-snug text-ink-400">{step.detail}</div>
                </div>
                {index < FLOW.length - 1 && (
                  <ChevronRight className="lp-flow-arrow absolute -right-2.5 top-1/2 hidden h-4 w-4 -translate-y-1/2 text-ink-300 lg:block" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
        <div className="grid gap-10 lg:grid-cols-[1fr_1.1fr] lg:items-center">
          <div>
            <div className="breadcrumb">Product tour</div>
            <h2 className="mt-1 text-[28px] font-semibold tracking-[-0.03em] text-ink-900 sm:text-[32px]">
              Every screen your team already needed
            </h2>
            <p className="mt-3 text-[14.5px] leading-relaxed text-ink-500">
              Routing, provider health, automations and AI recommendations — designed together, so
              the numbers always agree with each other.
            </p>

            <div className="mt-6 flex flex-wrap gap-1.5">
              {SHOWCASE.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setTab(item.id)}
                  className={
                    "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12px] font-medium transition-colors " +
                    (tab === item.id
                      ? "border-brand-400/60 bg-brand-500/10 text-brand-700"
                      : "border-ink-200 bg-card text-ink-500 hover:text-ink-900")
                  }
                >
                  <item.icon className="h-3.5 w-3.5" />
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="lp-window">
            <WindowBar url={"app.mailmatrix.io / " + tab} />
            <div className="p-3.5">
              <ShowcasePanel tab={tab} />
            </div>
          </div>
        </div>
      </section>

      <section className="border-y border-ink-200 bg-ink-100/50">
        <div className="mx-auto max-w-6xl px-5 py-12">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {METRICS.map((metric) => (
              <Metric key={metric.label} {...metric} />
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
        <div className="mx-auto max-w-2xl text-center">
          <div className="breadcrumb justify-center">Customers</div>
          <h2 className="mt-1 text-[28px] font-semibold tracking-[-0.03em] text-ink-900 sm:text-[32px]">
            Teams that stopped babysitting their sending
          </h2>
        </div>

        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {TESTIMONIALS.map((item) => (
            <figure key={item.name} className="surface flex h-full flex-col p-5">
              <div className="flex gap-0.5 text-warn-500">
                {Array.from({ length: 5 }).map((_, index) => (
                  <Star key={index} className="h-3.5 w-3.5 fill-current" />
                ))}
              </div>
              <blockquote className="mt-3 flex-1 text-[13px] leading-relaxed text-ink-600">
                “{item.quote}”
              </blockquote>
              <div className="mt-4 inline-flex w-fit items-center gap-1.5 rounded-full bg-brand-500/10 px-2.5 py-0.5 text-[10.5px] font-semibold text-brand-700">
                <TrendingIcon />
                {item.stat}
              </div>
              <figcaption className="mt-4 flex items-center gap-2.5 border-t border-ink-200 pt-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 text-[11px] font-bold text-brand-700">
                  {item.initials}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[12.5px] font-semibold text-ink-800">
                    {item.name}
                  </span>
                  <span className="block truncate text-[11px] text-ink-400">{item.role}</span>
                </span>
              </figcaption>
            </figure>
          ))}
        </div>
      </section>

      <section id="pricing" className="border-t border-ink-200 bg-ink-100/50">
        <div className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="max-w-xl">
              <div className="breadcrumb">Pricing</div>
              <h2 className="mt-1 text-[28px] font-semibold tracking-[-0.03em] text-ink-900 sm:text-[32px]">
                Priced for the volume you actually send
              </h2>
              <p className="mt-3 text-[14.5px] leading-relaxed text-ink-500">
                Every plan includes the orchestration engine, the agent fleet and deliverability
                monitoring. You only scale the limits.
              </p>
            </div>

            <div className="seg">
              <button
                onClick={() => setAnnual(false)}
                className={"seg-item " + (!annual ? "seg-item-active" : "")}
              >
                Monthly
              </button>
              <button
                onClick={() => setAnnual(true)}
                className={"seg-item " + (annual ? "seg-item-active" : "")}
              >
                Annual
                <span className="ml-1.5 rounded bg-brand-500/15 px-1 py-0.5 text-[10px] font-semibold text-brand-700">
                  -20%
                </span>
              </button>
            </div>
          </div>

          <div className="mt-9 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            {PLANS.map((plan) => {
              const price = annual ? plan.annual : plan.monthly;
              return (
                <article
                  key={plan.name}
                  className={
                    "surface relative flex h-full flex-col p-5 " +
                    (plan.featured ? "border-brand-400/70 ring-1 ring-brand-400/40" : "")
                  }
                >
                  {plan.featured && (
                    <span className="absolute -top-2.5 left-5 rounded-full bg-brand-500 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-white">
                      Most popular
                    </span>
                  )}
                  <h3 className="text-[14px] font-semibold text-ink-900">{plan.name}</h3>
                  <div className="mt-2 flex items-baseline gap-1">
                    {price === null ? (
                      <span className="text-[26px] font-semibold leading-none tracking-[-0.02em] text-ink-900">
                        Custom
                      </span>
                    ) : (
                      <>
                        <span className="text-[30px] font-semibold leading-none tracking-[-0.02em] text-ink-900">
                          ${price}
                        </span>
                        <span className="text-[12px] text-ink-400">/month</span>
                      </>
                    )}
                  </div>
                  <p className="mt-1.5 text-[11px] text-ink-400">
                    {price === null
                      ? "Tailored to your volume"
                      : annual
                        ? "billed annually"
                        : "billed monthly"}
                  </p>
                  <p className="mt-2 text-[12px] leading-relaxed text-ink-500">{plan.tagline}</p>
                  <ul className="mt-4 flex-1 space-y-2">
                    {plan.features.map((feature) => (
                      <li
                        key={feature}
                        className="flex items-start gap-2 text-[12.5px] text-ink-600"
                      >
                        <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-600" />
                        {feature}
                      </li>
                    ))}
                  </ul>
                  <button
                    onClick={plan.name === "Enterprise" ? onDemo : onStart}
                    className={"mt-5 w-full " + (plan.featured ? "btn-primary" : "btn-ghost")}
                  >
                    {plan.cta}
                  </button>
                </article>
              );
            })}
          </div>

          <p className="mt-6 text-center text-[11.5px] text-ink-400">
            14-day trial on every plan. No card required.
          </p>
        </div>
      </section>

      <section id="faq" className="mx-auto max-w-3xl px-5 py-16 lg:py-20">
        <div className="text-center">
          <div className="breadcrumb justify-center">FAQ</div>
          <h2 className="mt-1 text-[28px] font-semibold tracking-[-0.03em] text-ink-900 sm:text-[32px]">
            Questions we get before the trial
          </h2>
        </div>

        <div className="mt-8 divide-y divide-ink-200 overflow-hidden rounded-card border border-ink-200 bg-card">
          {FAQS.map((item, index) => (
            <div key={item.q}>
              <button
                onClick={() => setFaqOpen(faqOpen === index ? -1 : index)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left"
                aria-expanded={faqOpen === index}
              >
                <span className="text-[13px] font-medium text-ink-800">{item.q}</span>
                <ChevronDown
                  className={
                    "h-4 w-4 shrink-0 text-ink-400 transition-transform " +
                    (faqOpen === index ? "rotate-180" : "")
                  }
                />
              </button>
              {faqOpen === index && (
                <p className="px-4 pb-4 text-[12.5px] leading-relaxed text-ink-500">{item.a}</p>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 pb-16 lg:pb-20">
        <div className="lp-cta overflow-hidden px-6 py-12 text-center sm:px-10">
          <div className="lp-glow" aria-hidden="true" />
          <div className="relative">
            <h2 className="text-[27px] font-semibold tracking-[-0.03em] text-ink-900 sm:text-[32px]">
              See your first campaign orchestrated in minutes
            </h2>
            <p className="mx-auto mt-2.5 max-w-xl text-[14px] leading-relaxed text-ink-500">
              Open the demo workspace — no account, no card — or start a trial and bring your own
              providers.
            </p>
            <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
              <button onClick={onDemo} className="btn-primary">
                <Play className="h-4 w-4" />
                Open demo workspace
              </button>
              <button onClick={onStart} className="btn-ghost">
                Start free trial
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-[11.5px] text-ink-500">
              {["Live sandbox", "No sending", "Full product"].map((item) => (
                <span key={item} className="flex items-center gap-1.5">
                  <CheckCircle className="h-3.5 w-3.5 text-brand-600" />
                  {item}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      <footer className="border-t border-ink-200 bg-ink-100/60">
        <div className="mx-auto max-w-6xl px-5 py-12">
          <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
            <div>
              <div className="flex items-center gap-2.5">
                <span className="brand-mark">
                  <Mail className="h-[18px] w-[18px]" />
                </span>
                <span className="text-[14px] font-bold tracking-tight text-ink-900">MailMatrix</span>
              </div>
              <p className="mt-3 max-w-xs text-[12px] leading-relaxed text-ink-500">
                Intelligent email orchestration at scale. Every provider, campaign and reply in one
                queue.
              </p>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {["SOC 2", "GDPR", "99.99%"].map((item) => (
                  <span key={item} className="chip">
                    {item}
                  </span>
                ))}
              </div>
            </div>

            {[
              {
                title: "Product",
                links: ["Overview", "Features", "Providers", "Automations", "AI insights"],
              },
              {
                title: "Company",
                links: ["About", "Customers", "Careers", "Contact"],
              },
              {
                title: "Resources",
                links: ["Docs", "API reference", "Status", "Security"],
              },
            ].map((column) => (
              <div key={column.title}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-400">
                  {column.title}
                </div>
                <ul className="mt-3 space-y-2">
                  {column.links.map((link) => (
                    <li key={link}>
                      <a
                        href="#product"
                        className="text-[12.5px] text-ink-600 transition-colors hover:text-ink-900"
                      >
                        {link}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="mt-10 flex flex-col gap-3 border-t border-ink-200 pt-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-[11.5px] text-ink-400">
              © {new Date().getFullYear()} MailMatrix. All rights reserved.
            </p>
            <div className="flex items-center gap-4 text-[11.5px] text-ink-500">
              <button onClick={onSignIn} className="hover:text-ink-900">
                Sign in
              </button>
              <button onClick={onDemo} className="hover:text-ink-900">
                Demo
              </button>
              <a href="#pricing" className="hover:text-ink-900">
                Pricing
              </a>
              <span className="flex items-center gap-1.5">
                <Globe className="h-3.5 w-3.5" />
                Global
              </span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

function TrendingIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
      <path d="M3 17l6-6 4 4 8-8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M15 7h6v6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}