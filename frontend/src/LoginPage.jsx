import { useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Mail,
  Play,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";

import { encodeBasic } from "./auth.js";

const BRAND_NAME = "MailMatrix";

const HIGHLIGHTS = [
  {
    icon: Workflow,
    title: "Every provider, one queue",
    body: "Route across SMTP pools with pacing, caps and failover already applied.",
  },
  {
    icon: Sparkles,
    title: "An agent fleet that ships",
    body: "Drafts, sends, classifies replies and follows up without a handoff.",
  },
  {
    icon: ShieldCheck,
    title: "Deliverability you can see",
    body: "Inbox placement, reputation and provider health in real time.",
  },
];

export default function LoginPage({
  onSuccess,
  initialUser = "",
  reason = null,
  onDemo,
  demoBusy = false,
  onHome,
}) {
  const [user, setUser] = useState(initialUser);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [capsLock, setCapsLock] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;

    const trimmed = user.trim();
    setError(null);

    if (!trimmed || !password) {
      setError("Enter your username and password to continue.");
      return;
    }

    setBusy(true);
    const header = `Basic ${encodeBasic(trimmed, password)}`;

    try {
      const response = await fetch("/api/state", { headers: { Authorization: header } });
      if (response.ok) {
        onSuccess({ user: trimmed, password, remember });
        return;
      }
      if (response.status === 401) {
        setError("Invalid username or password.");
      } else {
        setError(`Sign-in failed (${response.status}). Please try again.`);
      }
    } catch {
      setError("Could not reach the server. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-shell">
      <section className="login-brand">
        <div className="login-mesh" aria-hidden="true" />
        <div className="relative flex h-full flex-col justify-between gap-10 p-8 lg:p-12">
          <div className="flex items-center gap-2.5">
            <span className="brand-mark">
              <Mail className="h-[18px] w-[18px]" />
            </span>
            <span className="text-[15px] font-bold tracking-tight text-ink-900">{BRAND_NAME}</span>
          </div>

          <div className="max-w-md">
            <h1 className="text-[30px] font-semibold leading-[1.12] tracking-[-0.035em] text-ink-900 lg:text-[38px]">
              Intelligent email orchestration at scale.
            </h1>
            <p className="mt-3.5 text-[14px] leading-relaxed text-ink-500">
              One control centre for every provider, campaign and reply — with an agent fleet that
              drafts, sends and answers for you.
            </p>

            <ul className="mt-8 space-y-4">
              {HIGHLIGHTS.map((item) => (
                <li key={item.title} className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] border border-brand-300/40 bg-brand-500/10 text-brand-700">
                    <item.icon className="h-4 w-4" />
                  </span>
                  <div className="min-w-0">
                    <div className="text-[13px] font-semibold text-ink-800">{item.title}</div>
                    <div className="mt-0.5 text-[12.5px] leading-relaxed text-ink-500">{item.body}</div>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <div className="flex items-center gap-2 text-[11.5px] text-ink-400">
            <Lock className="h-3.5 w-3.5" />
            Access is restricted to your workspace
          </div>
        </div>
      </section>

      <section className="login-panel">
        <div className="login-card animate-fade-in">
          {onHome && (
            <button
              type="button"
              onClick={onHome}
              className="mb-6 inline-flex items-center gap-1.5 text-[12px] font-medium text-ink-500 transition-colors hover:text-ink-900"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Back to home
            </button>
          )}

          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <span className="brand-mark">
              <Mail className="h-[18px] w-[18px]" />
            </span>
            <span className="text-[15px] font-bold tracking-tight text-ink-900">{BRAND_NAME}</span>
          </div>

          <h2 className="text-[22px] font-semibold tracking-[-0.02em] text-ink-900">Sign in</h2>
          <p className="mt-1.5 text-[13px] leading-relaxed text-ink-500">
            Enter the credentials for this workspace to open the control centre.
          </p>

          <form onSubmit={submit} className="mt-7 space-y-4" noValidate>
            {reason && (
              <div className="notice notice-info" role="status">
                {reason}
              </div>
            )}

            {error && (
              <div className="notice notice-error flex items-start gap-2" role="alert">
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <label className="field-label">
              Username
              <input
                className="input mt-1"
                value={user}
                onChange={(event) => setUser(event.target.value)}
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                autoFocus
                disabled={busy}
                aria-invalid={Boolean(error)}
              />
            </label>

            <label className="field-label">
              Password
              <span className="relative mt-1 block">
                <input
                  className="input pr-11"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  onKeyUp={(event) => setCapsLock(event.getModifierState?.("CapsLock") || false)}
                  autoComplete="current-password"
                  disabled={busy}
                  aria-invalid={Boolean(error)}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  className="login-reveal"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  title={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </span>
            </label>

            {capsLock && (
              <p className="-mt-1 text-[11.5px] font-medium text-warn-700">Caps Lock is on.</p>
            )}

            <div className="flex items-center justify-between gap-3">
              <label className="flex items-center gap-2 text-[12.5px] text-ink-600">
                <input
                  type="checkbox"
                  className="checkbox"
                  checked={remember}
                  onChange={(event) => setRemember(event.target.checked)}
                  disabled={busy}
                />
                Keep me signed in
              </label>
            </div>

            <button type="submit" className="btn-primary w-full" disabled={busy}>
              {busy ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Signing in…
                </>
              ) : (
                <>
                  Sign in
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </form>

          {onDemo && (
            <>
              <div className="my-5 flex items-center gap-3">
                <span className="h-px flex-1 bg-ink-200" />
                <span className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-ink-400">
                  or
                </span>
                <span className="h-px flex-1 bg-ink-200" />
              </div>

              <button
                type="button"
                onClick={onDemo}
                className="btn-ghost w-full"
                disabled={demoBusy || busy}
              >
                {demoBusy ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Opening demo…
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4" />
                    Explore the live demo
                  </>
                )}
              </button>
              <p className="mt-2 text-center text-[11px] text-ink-400">
                A seeded workspace. No account, no card, no sending.
              </p>
            </>
          )}

          <p className="mt-7 border-t border-ink-200 pt-5 text-[11.5px] leading-relaxed text-ink-400">
            Need access? Ask your workspace owner to provision an account. Sessions are protected
            with HTTP Basic authentication.
          </p>
        </div>
      </section>
    </div>
  );
}