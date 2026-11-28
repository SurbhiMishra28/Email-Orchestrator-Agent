import {
  Activity,
  ArrowRight,
  BarChart3,
  Brain,
  CheckCircle,
  ChevronRight,
  Gauge,
  Layers,
  Mail,
  Play,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Star,
  Workflow,
  Zap,
} from "lucide-react";

const NAV = [
  { label: "Product", href: "#product" },
  { label: "Features", href: "#features" },
  { label: "Pricing", href: "#pricing" },
];

const TRUST = [
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
    body: "Every send picks the best provider automatically, scored on live deliverability and reputation.",
  },
  {
    icon: RefreshCw,
    title: "Smart failover",
    body: "A provider degrades, the queue reroutes in seconds. No dropped campaigns, no 3 a.m. pages.",
  },
  {
    icon: Gauge,
    title: "Deliverability intelligence",
    body: "Inbox placement, bounce reasons and domain reputation in one view, per provider and per campaign.",
  },
  {
    icon: Layers,
    title: "Multi-provider control",
    body: "SMTP, Gmail API and Resend pools managed from one control centre with real health scores.",
  },
  {
    icon: Workflow,
    title: "Campaign automation",
    body: "A visual builder for triggers, conditions, delays and AI decisions — no glue scripts.",
  },
  {
    icon: Sparkles,
    title: "AI send optimisation",
    body: "Send-time and subject experiments that learn from your replies, not from generic benchmarks.",
  },
];

const FLOW = [
  { icon: Mail, label: "Campaign" },
  { icon: Workflow, label: "Routing engine" },
  { icon: Layers, label: "SMTP pool" },
  { icon: ShieldCheck, label: "Provider selection" },
  { icon: Activity, label: "Delivery monitoring" },
  { icon: BarChart3, label: "Analytics & AI" },
];

const METRICS = [
  { value: "99.2%", label: "Median inbox placement" },
  { value: "18%", label: "Lift from AI routing" },
  { value: "6.4M", label: "Emails orchestrated weekly" },
  { value: "<2s", label: "Failover time" },
];

const TESTIMONIALS = [
  {
    quote:
      "We run four providers across three brands. MailMatrix is the first tool that made that boring instead of terrifying.",
    name: "Ada Lovelace",
    role: "Head of Growth, Northwind",
    initials: "AL",
  },
  {
    quote:
      "The reply handling alone paid for it. Positive replies get answered while we sleep, and nothing slips.",
    name: "Grace Hopper",
    role: "CTO, Hopper Labs",
    initials: "GH",
  },
  {
    quote:
      "Deliverability used to be a monthly fire drill. Now it is a number on a dashboard that I actually trust.",
    name: "Alan Turing",
    role: "Founder, Bletchley",
    initials: "AT",
  },
];

const PLANS = [
  {
    name: "Starter",
    price: "$29",
    tagline: "For a first list and a first pipeline.",
    features: ["5 SMTP providers", "25k emails / month", "Basic analytics", "Email support"],
    cta: "Start free trial",
  },
  {
    name: "Professional",
    price: "$99",
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
    price: "$299",
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
    price: "Custom",
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

function HeroDashboard() {
  const providers = [
    { name: "Mailgun", score: 98, volume: "42k", tone: "bg-brand-500" },
    { name: "SendGrid", score: 94, volume: "31k", tone: "bg-info-500" },
    { name: "Amazon SES", score: 91, volume: "18k", tone: "bg-brand-400" },
  ];

  return (
    <div className="lp-dashboard">
      <div className="lp-dashboard-bar">
        <span className="h-2 w-2 rounded-full bg-danger-400" />
        <span className="h-2 w-2 rounded-full bg-warn-400" />
        <span className="h-2 w-2 rounded-full bg-brand-400" />
        <span className="ml-2 truncate text-[10.5px] text-ink-400">app.mailmatrix.io / overview</span>
      </div>

      <div className="grid grid-cols-3 gap-2 border-b border-ink-200 px-3 py-2.5">
        {[
          { label: "Sent", value: "284k" },
          { label: "Inbox rate", value: "99.2%" },
          { label: "AI score", value: "94" },
        ].map((tile) => (
          <div key={tile.label} className="rounded-lg border border-ink-200 bg-ink-50 px-2 py-1.5">
            <div className="text-[9px] font-semibold uppercase tracking-[0.08em] text-ink-400">
              {tile.label}
            </div>
            <div className="text-[14px] font-semibold tabular-nums text-ink-900">{tile.value}</div>
          </div>
        ))}
      </div>

      <div className="space-y-1.5 px-3 py-2.5">
        {providers.map((provider) => (
          <div key={provider.name} className="flex items-center gap-2">
            <span className="w-[74px] shrink-0 truncate text-[10.5px] font-medium text-ink-700">
              {provider.name}
            </span>
            <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-200">
              <span className={"block h-full rounded-full " + provider.tone} style={{ width: provider.score + "%" }} />
            </span>
            <span className="w-8 shrink-0 text-right text-[10px] tabular-nums text-ink-500">
              {provider.score}
            </span>
            <span className="w-8 shrink-0 text-right text-[10px] tabular-nums text-ink-400">
              {provider.volume}
            </span>
          </div>
        ))}
      </div>

      <div className="border-t border-ink-200 px-3 py-2.5">
        <div className="mb-1.5 flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-[0.1em] text-ink-400">
          <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
          Live agent activity
        </div>
        {[
          ["Composer", "drafted 12 intros", "ok"],
          ["Sender", "delivered via Mailgun", "ok"],
          ["Reply analyst", "classified 3 replies", "info"],
        ].map(([agent, detail, tone]) => (
          <div key={agent} className="flex items-center gap-2 py-0.5 text-[10px]">
            <span
              className={
                "h-1.5 w-1.5 shrink-0 rounded-full " +
                (tone === "ok" ? "bg-brand-500" : "bg-info-500")
              }
            />
            <span className="w-[70px] shrink-0 font-semibold text-ink-700">{agent}</span>
            <span className="truncate text-ink-500">{detail}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function LandingPage({ onSignIn, onDemo, onStart }) {
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

          <nav className="hidden items-center gap-6 md:flex">
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
            <button onClick={onSignIn} className="btn-ghost btn-sm">
              Sign in
            </button>
            <button onClick={onStart} className="btn-primary btn-sm">
              Start free trial
            </button>
          </div>
        </div>
      </header>

      <section className="relative overflow-hidden">
        <div className="lp-mesh" aria-hidden="true" />
        <div className="relative mx-auto grid max-w-6xl items-center gap-10 px-5 py-16 lg:grid-cols-[1.05fr_1fr] lg:py-24">
          <div>
            <span className="chip border-brand-300/50 bg-brand-500/10 text-brand-700">
              <Sparkles className="h-3 w-3" />
              Intelligent email orchestration
            </span>
            <h1 className="mt-5 text-[34px] font-semibold leading-[1.08] tracking-[-0.035em] text-ink-900 sm:text-[44px]">
              Orchestrate email campaigns at scale
            </h1>
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-ink-500">
              Manage multiple SMTP providers, automate outreach workflows, monitor deliverability and
              maximise inbox placement from one intelligent platform.
            </p>

            <div className="mt-7 flex flex-wrap items-center gap-3">
              <button onClick={onStart} className="btn-primary">
                Start free trial
                <ArrowRight className="h-4 w-4" />
              </button>
              <button onClick={onDemo} className="btn-ghost">
                <Play className="h-4 w-4" />
                Book a demo
              </button>
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 text-[12px] text-ink-500">
              {["No credit card", "Live demo workspace", "Cancel anytime"].map((item) => (
                <span key={item} className="flex items-center gap-1.5">
                  <CheckCircle className="h-3.5 w-3.5 text-brand-600" />
                  {item}
                </span>
              ))}
            </div>
          </div>

          <div className="relative">
            <div className="lp-glow" aria-hidden="true" />
            <HeroDashboard />
            <div className="lp-float lp-float-a">
              <Zap className="h-3.5 w-3.5 text-brand-600" />
              AI routing active
            </div>
            <div className="lp-float lp-float-b">
              <ShieldCheck className="h-3.5 w-3.5 text-brand-600" />
              99.99% uptime
            </div>
          </div>
        </div>
      </section>

      <section className="border-y border-ink-200 bg-ink-100/60">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-x-8 gap-y-3 px-5 py-5">
          {TRUST.map((item) => (
            <span key={item} className="flex items-center gap-1.5 text-[11.5px] font-medium text-ink-500">
              <ShieldCheck className="h-3.5 w-3.5 text-brand-600" />
              {item}
            </span>
          ))}
        </div>
      </section>

      <section id="product" className="mx-auto max-w-6xl px-5 py-16">
        <div className="max-w-2xl">
          <div className="breadcrumb">Platform</div>
          <h2 className="mt-1 text-[26px] font-semibold tracking-[-0.025em] text-ink-900">
            One control centre for every send
          </h2>
          <p className="mt-2 text-[14px] leading-relaxed text-ink-500">
            Providers, campaigns, replies and deliverability used to live in four tools. They now
            live in one queue with an agent fleet behind it.
          </p>
        </div>

        <div id="features" className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {FEATURES.map((feature) => (
            <article key={feature.title} className="surface p-5 transition-colors hover:border-brand-300/60">
              <span className="stat-icon bg-brand-50 text-brand-600">
                <feature.icon className="h-4 w-4" />
              </span>
              <h3 className="mt-3 text-[14px] font-semibold text-ink-900">{feature.title}</h3>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-500">{feature.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="border-y border-ink-200 bg-ink-100/50">
        <div className="mx-auto max-w-6xl px-5 py-16">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <div className="breadcrumb">How it works</div>
              <h2 className="mt-1 text-[26px] font-semibold tracking-[-0.025em] text-ink-900">
                From campaign to inbox, in one pass
              </h2>
            </div>
            <span className="chip">
              <Activity className="h-3 w-3" />
              Live routing
            </span>
          </div>

          <div className="mt-8 flex flex-col gap-2 lg:flex-row lg:items-stretch">
            {FLOW.map((step, index) => (
              <div key={step.label} className="flex min-w-0 flex-1 items-center gap-2">
                {index > 0 && <ChevronRight className="hidden h-4 w-4 shrink-0 text-ink-300 lg:block" />}
                <div className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-ink-200 bg-card px-3 py-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] border border-brand-300/40 bg-brand-500/10 text-brand-700">
                    <step.icon className="h-4 w-4" />
                  </span>
                  <span className="truncate text-[12.5px] font-medium text-ink-700">{step.label}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-16">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {METRICS.map((metric) => (
            <div key={metric.label} className="surface p-5">
              <div className="text-[26px] font-semibold leading-none tracking-[-0.02em] text-ink-900">
                {metric.value}
              </div>
              <div className="mt-2 text-[12px] leading-snug text-ink-500">{metric.label}</div>
            </div>
          ))}
        </div>

        <div className="mt-14 grid grid-cols-1 gap-4 md:grid-cols-3">
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
              <figcaption className="mt-4 flex items-center gap-2.5 border-t border-ink-200 pt-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 text-[11px] font-bold text-brand-700">
                  {item.initials}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[12.5px] font-semibold text-ink-800">{item.name}</span>
                  <span className="block truncate text-[11px] text-ink-400">{item.role}</span>
                </span>
              </figcaption>
            </figure>
          ))}
        </div>

        <p className="mt-6 text-center text-[11.5px] text-ink-400">
          Trusted by modern growth teams.
        </p>
      </section>

      <section id="pricing" className="border-t border-ink-200 bg-ink-100/50">
        <div className="mx-auto max-w-6xl px-5 py-16">
          <div className="max-w-2xl">
            <div className="breadcrumb">Pricing</div>
            <h2 className="mt-1 text-[26px] font-semibold tracking-[-0.025em] text-ink-900">
              Priced for the volume you actually send
            </h2>
            <p className="mt-2 text-[14px] leading-relaxed text-ink-500">
              Every plan includes the orchestration engine, the agent fleet and deliverability
              monitoring. You only scale the limits.
            </p>
          </div>

          <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            {PLANS.map((plan) => (
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
                  <span className="text-[28px] font-semibold leading-none tracking-[-0.02em] text-ink-900">
                    {plan.price}
                  </span>
                  {plan.price.startsWith("$") && (
                    <span className="text-[12px] text-ink-400">/month</span>
                  )}
                </div>
                <p className="mt-2 text-[12px] leading-relaxed text-ink-500">{plan.tagline}</p>
                <ul className="mt-4 flex-1 space-y-2">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex items-start gap-2 text-[12.5px] text-ink-600">
                      <CheckCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-600" />
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
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-16">
        <div className="agent-hero overflow-hidden px-6 py-10 text-center sm:px-10">
          <div className="agent-hero-glow" aria-hidden="true" />
          <div className="relative">
            <h2 className="text-[26px] font-semibold tracking-[-0.025em] text-ink-900">
              See your first campaign orchestrated in minutes
            </h2>
            <p className="mx-auto mt-2 max-w-xl text-[14px] leading-relaxed text-ink-500">
              Open the demo workspace — no account, no card — or start a trial and bring your own
              providers.
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
              <button onClick={onDemo} className="btn-primary">
                <Play className="h-4 w-4" />
                Open demo workspace
              </button>
              <button onClick={onStart} className="btn-ghost">
                Start free trial
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </section>

      <footer className="border-t border-ink-200 bg-ink-100/60">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-8 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2.5">
            <span className="brand-mark">
              <Mail className="h-[18px] w-[18px]" />
            </span>
            <span className="text-[14px] font-bold tracking-tight text-ink-900">MailMatrix</span>
            <span className="ml-2 text-[11.5px] text-ink-400">
              Intelligent email orchestration at scale
            </span>
          </div>
          <div className="flex items-center gap-4 text-[12px] text-ink-500">
            <button onClick={onSignIn} className="hover:text-ink-900">
              Sign in
            </button>
            <button onClick={onDemo} className="hover:text-ink-900">
              Demo
            </button>
            <a href="#pricing" className="hover:text-ink-900">
              Pricing
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}