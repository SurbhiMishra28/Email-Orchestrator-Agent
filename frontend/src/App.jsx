import { useState, useEffect, useCallback, useRef, useMemo } from "react";

import { Mail, Users, FileText, Inbox, Settings, Play, BarChart3, Activity, Send, AlertCircle, Upload, Pencil, Sparkles, PenLine, Brain, Copy, Trash2, Shield, CheckCircle, XCircle, AlertTriangle, Loader2, RefreshCw, Filter, Search, Plus, Info, Check, TrendingUp, MoreHorizontal, Folder, FolderPlus, MoveRight, SlidersHorizontal, Menu, X } from "lucide-react";



const BRAND_NAME = "MailMatrix";

import { basicAuthHeader, getBasicAuth, requestCredentials, setBasicAuth } from "./auth.js";

// Brevo-style opening screen: the wordmark dominates, then the app takes over.
function Splash(){
  return (
    <div className="splash" role="status" aria-live="polite" aria-label={`${BRAND_NAME} is loading`}>
      <div className="splash-word">{BRAND_NAME}</div>
      <div className="splash-tag">Email Orchestrator</div>
      <div className="splash-bar"><span/></div>
    </div>
  );
}

const KNOWN_VIEWS = [
  "overview", "agents", "contacts", "drafts", "templates", "inbox",
  "verifications", "automation", "team", "settings", "campaigns", "experiments",
  "history",
];

const api = async (path, opts = {}) => {

  const authHeader = basicAuthHeader();

  const response = await fetch(path, {

    ...opts,

    headers: {
      "Content-Type": "application/json",
      ...(authHeader ? { Authorization: authHeader } : {}),
      ...opts.headers,
    },

  });

  if (response.status === 401) {
    // Credentials are missing, wrong, or were cleared. Drop them and let the
    // shell ask again rather than surfacing "Request failed (401)".
    requestCredentials();
    const err = new Error("Request failed (401)");
    err.status = 401;
    throw err;
  }

  const body = await response.text();

  let data;

  try {

    data = body ? JSON.parse(body) : null;

  } catch {

    if (!response.ok) {

      const err = new Error(`Request failed (${response.status})`);
      err.status = response.status;
      throw err;

    }

    const err = new Error(`Invalid JSON response (${response.status})`);
    err.status = response.status;
    throw err;

  }

  if (!response.ok) {

    const errorMsg = (data && data.detail) || (body && body.trim()) || `Request failed (${response.status})`;

    const err = new Error(typeof errorMsg === "string" ? errorMsg : JSON.stringify(errorMsg));
    err.status = response.status;

    throw err;

  }

  return data;

};



const normalizeState = (s) => ({

  ...s,

  contacts: Array.isArray(s?.contacts) ? s.contacts : [],

  drafts: Array.isArray(s?.drafts) ? s.drafts : [],

  events: Array.isArray(s?.events) ? s.events : [],

  logs: Array.isArray(s?.logs) ? s.logs : [],

  tools: Array.isArray(s?.tools) ? s.tools : [],

  analytics: s?.analytics || {},

  usage: s?.usage || {},

});



const inputCls = "input";

const btnGhost = "btn-ghost";

const btnPrimary = "btn-primary";



// static class map so Tailwind can see every color at build time

const STAT_COLORS = {

  blue: "text-info-600",

  green: "text-brand-600",

  red: "text-danger-600",

  yellow: "text-warn-600",

  gray: "text-ink-600",

};

const STAT_ICON_TONES = {

  blue: "bg-info-50 text-info-600 border-info-100",

  green: "bg-brand-50 text-brand-600 border-brand-100",

  red: "bg-danger-50 text-danger-600 border-danger-100",

  yellow: "bg-warn-50 text-warn-600 border-warn-100",

  gray: "bg-ink-100 text-ink-500 border-ink-200",

};



function NavItem({icon:Icon,label,active,onClick,badge}){

  return (

    <button onClick={onClick} title={label} className={"group "+(active?"rail-link-active":"rail-link")} aria-current={active?"page":undefined}>

      <Icon className={"h-[18px] w-[18px] shrink-0 "+(active?"text-brand-600":"text-ink-400 group-hover:text-ink-600")}/>

      <span className="flex-1 truncate text-[13.5px]">{label}</span>

      {badge?<span className={"shrink-0 rounded-full px-1.5 text-[11px] font-semibold tabular-nums "+(active?"bg-brand-100 text-brand-700":"bg-ink-100 text-ink-500")}>{badge}</span>:null}

    </button>

  );

}



const STATUS_STYLES = {

  sent: "badge-sent",

  blocked: "badge-blocked",

  failed: "badge-failed",

  draft: "badge-draft",

  sending: "badge-sending",

  scheduled: "badge border-info-200 bg-info-50 text-info-700",

  paused: "badge border-warn-200 bg-warn-50 text-warn-700",

  cancelled: "badge border-ink-200 bg-ink-100 text-ink-500",

  active: "badge border-brand-200 bg-brand-50 text-brand-700",

};



function StatusPill({status="draft"}){

  const key=String(status||"draft").toLowerCase();

  return <span className={STATUS_STYLES[key]||STATUS_STYLES.draft}>{key}</span>;

}



function Card({title,children,action,subtitle,className=""}){

  return (

    <section className={"surface "+className}>

      {title&&(<div className="surface-head">

        <div>

          <h3 className="surface-title">{title}</h3>

          {subtitle&&<p className="mt-0.5 text-[12px] text-ink-500">{subtitle}</p>}

        </div>

        {action&&<div className="flex shrink-0 items-center gap-2">{action}</div>}

      </div>)}

      <div className="surface-body">{children}</div>

    </section>

  );

}

function StatCard({label,value,icon:Icon,color="blue",hint}){

  return (

    <div className="stat-tile">

      <div className="min-w-0">

        <div className="stat-label">{label}</div>

        <div className={"stat-value "+(STAT_COLORS[color]||STAT_COLORS.blue)}>{value}</div>

        {hint&&<div className="mt-0.5 truncate text-[12px] text-ink-500">{hint}</div>}

      </div>

      <div className={"stat-icon "+(STAT_ICON_TONES[color]||STAT_ICON_TONES.blue)}><Icon className="h-[18px] w-[18px]"/></div>

    </div>

  );

}



function LiveAgentActivity({enabled=true}){

  const [events,setEvents]=useState([]);

  const [connected,setConnected]=useState(false);

  const [paused,setPaused]=useState(false);

  useEffect(()=>{

    // A serverless host cannot hold a WebSocket open, so the API reports the
    // capability in /api/state. Connecting anyway would produce a reconnect
    // loop that fires every few seconds for the life of the page.
    if(!enabled) return;

    let socket=null;

    let retry=null;

    let closed=false;

    let attempts=0;

    const connect=()=>{

      if(closed) return;

      const proto=window.location.protocol==="https:"?"wss":"ws";

      socket=new WebSocket(`${proto}://${window.location.host}/ws/live-logs`);

      socket.onopen=()=>{ setConnected(true); attempts=0; };

      socket.onmessage=(msg)=>{

        try{

          const event=JSON.parse(msg.data);

          setEvents(prev=>[event,...prev].slice(0,60));

        }catch{ /* ignore malformed frames */ }

      };

      socket.onclose=()=>{

        setConnected(false);

        if(!closed){

          attempts+=1;

          retry=setTimeout(connect,Math.min(30000,1000*attempts));

        }

      };

      socket.onerror=()=>{ try{ socket.close(); }catch{} };

    };

    connect();

    return ()=>{ closed=true; clearTimeout(retry); try{ socket?.close(); }catch{} };

  },[enabled]);

  const visible=paused?[]:events;

  const running=new Set(visible.filter(e=>e.scope==="agent"&&e.status==="started").map(e=>e.agent));

  const colour=(status)=>status==="completed"?"text-brand-600":status==="failed"?"text-danger-600":"text-info-600";

  return (

    <Card title="Live agent activity">

      <div className="mb-3 flex items-center justify-between">

        <div className="flex items-center gap-2 text-[12px]">

          <span className={"h-2 w-2 rounded-full "+(enabled&&connected?"bg-brand-500":"bg-ink-300")}/>

          <span className="text-ink-600">{!enabled?"Unavailable on this host":connected?"Streaming":"Disconnected"}</span>

          {enabled&&running.size>0&&<span className="font-medium text-info-600">{running.size} running</span>}

        </div>

        <div className="flex items-center gap-1">

          <button onClick={()=>setPaused(p=>!p)} className="btn-ghost btn-sm">

            {paused?"Resume":"Pause"}

          </button>

          <button onClick={()=>setEvents([])} className="btn-ghost btn-sm">Clear</button>

        </div>

      </div>

      {!enabled&&(

        <p className="text-[12px] text-ink-500">
          Live streaming needs a long-lived process. This deployment runs on a
          serverless host, so activity is available from the activity log and
          each send is reported in the queue results.
        </p>

      )}

      {enabled&& (

      <div className="max-h-80 space-y-1 overflow-y-auto font-mono text-[11.5px]">

        {visible.map(event=>(

          <div key={event.id} className="flex items-start gap-2 border-b border-ink-100 pb-1 last:border-0">

            <span className="shrink-0 text-ink-400">{new Date(event.timestamp).toLocaleTimeString()}</span>

            <span className={"shrink-0 font-medium "+colour(event.status)}>{event.status}</span>

            <span className="truncate text-ink-800">{event.agent}{event.scope==="method"?`.${event.method}`:""}</span>

          </div>

        ))}

        {visible.length===0&&<p className="text-ink-500">No agent activity yet. Run the queue or send an email to see events.</p>}

      </div>

      )}

    </Card>

  );

}



function AnalyticsChart({series}){

  if(!series.length){

    return <p className="text-[12px] text-ink-500">No sending activity yet.</p>;

  }

  const max=Math.max(1,...series.map(d=>Math.max(d.sent||0,d.replied||0)));

  const label=(iso)=>{ const [,m,d]=iso.split("-"); return `${m}/${d}`; };

  return (

    <div>

      <div className="flex items-end gap-1 h-40">

        {series.map(day=>{

          const sent=day.sent||0;

          const replied=day.replied||0;

          return (

            <div key={day.date} className="flex-1 flex flex-col items-center justify-end gap-0.5" title={`${day.date}: ${sent} sent, ${replied} replied`}>

              <div className="w-full flex items-end justify-center gap-0.5" style={{height:"100%"}}>

                <div className="w-1/2 rounded-t bg-brand-500/80" style={{height:`${Math.max(sent?4:0,(sent/max)*100)}%`}}/>

                <div className="w-1/2 rounded-t bg-info-500/70" style={{height:`${Math.max(replied?4:0,(replied/max)*100)}%`}}/>

              </div>

              <span className="whitespace-nowrap text-[10px] tabular-nums text-ink-400">{label(day.date)}</span>

            </div>

          );

        })}

      </div>

      <div className="mt-3 flex items-center gap-4 text-[12px] text-ink-600">

        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-brand-500/80"/>Sent</span>

        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-info-500/70"/>Replied</span>

      </div>

    </div>

  );

}



function Pill({v}){

  return <span className="tag">{v}</span>;

}



// The four numbers that matter at a glance: what went out, what came back,
// which follow-ups were delivered, and how many clients actually want to talk.
function MetricSection({tone,icon:Icon,title,headline,headlineHint,rows,footer}){

  const tones={
    green:"bg-brand-50 text-brand-600 border-brand-100",
    blue:"bg-info-50 text-info-600 border-info-100",
    yellow:"bg-warn-50 text-warn-600 border-warn-100",
    red:"bg-danger-50 text-danger-600 border-danger-100",
  };

  return (
    <div className="surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="stat-label">{title}</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-[26px] font-semibold leading-none tabular-nums text-ink-900">{headline}</span>
            {headlineHint?<span className="truncate text-[12px] text-ink-500">{headlineHint}</span>:null}
          </div>
        </div>
        <div className={"stat-icon "+(tones[tone]||tones.blue)}><Icon className="h-[18px] w-[18px]"/></div>
      </div>
      <div className="mt-3 space-y-1.5 border-t border-ink-100 pt-2.5">
        {rows.map(([label,value])=>(
          <div key={label} className="flex items-center justify-between text-[12.5px]">
            <span className="text-ink-500">{label}</span>
            <span className="font-semibold tabular-nums text-ink-800">{value}</span>
          </div>
        ))}
      </div>
      {footer?<div className="mt-2 text-[11.5px] text-ink-400">{footer}</div>:null}
    </div>
  );
}



function PageHeader({title,subtitle,children,eyebrow}){

  return (

    <div className="page-head">

      <div className="min-w-0">

        {eyebrow&&<div className="breadcrumb mb-1">{eyebrow}</div>}

        <h1 className="page-title">{title}</h1>

        {subtitle&&<p className="page-subtitle">{subtitle}</p>}

      </div>

      {children&&<div className="flex flex-wrap items-center gap-2">{children}</div>}

    </div>

  );

}

function EmptyState({icon:Icon,title,description,action}){

  return (

    <div className="empty-state">

      {Icon&&<div className="stat-icon mb-1"><Icon className="h-5 w-5"/></div>}

      <p className="text-[14px] font-semibold text-ink-900">{title}</p>

      {description&&<p className="max-w-md text-[13px] text-ink-500">{description}</p>}

      {action}

    </div>

  );

}



function ErrorDisplay({err,onRetry}){

  return (

    <div className="flex h-full flex-col items-center justify-center p-8 text-center">

      <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full border border-danger-100 bg-danger-50 text-danger-600"><AlertCircle className="h-5 w-5"/></div>

      <h3 className="text-[15px] font-semibold text-ink-900">Something went wrong</h3>

      <p className="mt-1 mb-5 max-w-md text-[13px] text-ink-500">{err}</p>

      <button onClick={onRetry} className="btn-primary">Try again</button>

    </div>

  );

}






function EmailHistoryView({state,api,reload,notify}){

  const [filter,setFilter]=useState("all");

  const [busyId,setBusyId]=useState(null);

  const contacts=state.contacts||[];

  const contactById=useMemo(()=>Object.fromEntries(contacts.map(c=>[c.id,c])),[contacts]);

  // Sent and failed messages are the history. Drafts still in the queue are not
  // history yet, so they are excluded on purpose.
  const sent=(state.drafts||[]).filter(d=>d.status==="sent"||d.status==="failed");

  // Reply events tell us whether the recipient answered and how it was classified.
  // The classification lives at data.classification.reply_type (not data.reply_type).
  const replyByContact=useMemo(()=>{
    const map={};
    for(const e of (state.events||[])){
      if(e.type==="reply_event" && e.event_type==="reply_received" && e.contact_id!=null){
        const cls=(e.data||{}).classification||{};
        map[e.contact_id]={reply_type:cls.reply_type||null, at:e.timestamp};
      }
    }
    return map;
  },[state.events]);

  const rows=sent.map(d=>{
    const contact=contactById[d.contact_id]||{};
    const tags=contact.tags||[];
    const reply=replyByContact[d.contact_id];
    const interested=tags.includes("interested");
    const notInterested=tags.includes("not_interested");
    return {draft:d,contact,tags,reply,interested,notInterested};
  }).filter(r=>{
    if(filter==="all") return true;
    if(filter==="interested") return r.interested;
    if(filter==="not_interested") return r.notInterested;
    if(filter==="replied") return !!r.reply;
    if(filter==="no_reply") return !r.reply;
    return true;
  });

  const setTag=async(contact,tag,on)=>{
    if(!contact.id){ notify("Contact is missing for this email"); return; }
    setBusyId(contact.id);
    try{
      // interested and not_interested are mutually exclusive.
      if(on && tag==="interested" && (contact.tags||[]).includes("not_interested")){
        await api(`/api/contacts/${contact.id}/tags/not_interested`,{method:"DELETE"});
      }
      if(on && tag==="not_interested" && (contact.tags||[]).includes("interested")){
        await api(`/api/contacts/${contact.id}/tags/interested`,{method:"DELETE"});
      }
      if(on){
        await api(`/api/contacts/${contact.id}/tags`,{method:"POST",body:JSON.stringify({tags:[tag]})});
      }else{
        await api(`/api/contacts/${contact.id}/tags/${tag}`,{method:"DELETE"});
      }
      notify(on?`Marked ${tag.replace("_"," ")}`:`Removed ${tag.replace("_"," ")}`);
      await reload();
    }catch(e){ notify(e?.message||String(e)); }
    finally{ setBusyId(null); }
  };

  const stats={
    total:sent.length,
    replied:rows.filter(r=>r.reply).length,
    interested:rows.filter(r=>r.interested).length,
  };

  return (
    <div className="space-y-4">
      <PageHeader title="Email history" subtitle="Every message that left your mailbox, with who replied and who is interested." eyebrow="Campaigns">
        <button onClick={reload} className="btn-secondary"><RefreshCw className="h-3.5 w-3.5"/>Refresh</button>
      </PageHeader>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <StatCard label="Sent" value={stats.total} icon={Send} color="green" hint="All time"/>
        <StatCard label="Replied" value={stats.replied} icon={Mail} color="blue" hint="Got a response"/>
        <StatCard label="Interested" value={stats.interested} icon={CheckCircle} color="green" hint="Tagged interested"/>
      </div>

      <Card title="History" className="overflow-hidden">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <select className="select w-full sm:w-56" value={filter} onChange={e=>setFilter(e.target.value)}>
            <option value="all">All</option>
            <option value="replied">Replied</option>
            <option value="no_reply">No reply</option>
            <option value="interested">Interested</option>
            <option value="not_interested">Not interested</option>
          </select>
        </div>

        <div className="-mx-5 -mb-4 overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th className="w-64 min-w-64">To</th>
                <th className="w-40 min-w-40">Subject</th>
                <th className="w-32 min-w-32">Status</th>
                <th className="w-28 min-w-28">Reply</th>
                <th className="w-40 min-w-40">Sent</th>
                <th className="w-44 min-w-44">Manage</th>
              </tr>
            </thead>
            <tbody>
              {rows.length===0&&(
                <tr><td colSpan={6} className="table-empty">No sent emails yet. Add a contact and press Run.</td></tr>
              )}
              {rows.map(({draft,contact,reply,interested,notInterested})=>(
                <tr key={draft.id}>
                  <td className="max-w-64 truncate">
                    <div className="font-medium text-ink-900">{contact.name||contact.email||"Unknown"}</div>
                    <div className="truncate text-[12px] text-ink-500">{contact.email||""}</div>
                  </td>
                  <td className="max-w-40 truncate text-[13px]">{draft.subject}</td>
                  <td>{getStatusBadge(draft.status)}</td>
                  <td>{reply?<Pill v={reply.reply_type||"replied"}/>:<span className="text-[12px] text-ink-400">No reply</span>}</td>
                  <td className="whitespace-nowrap text-[12px] text-ink-500">{draft.sent_at?new Date(draft.sent_at).toLocaleString():"-"}</td>
                  <td>
                    <div className="flex items-center gap-0.5">
                      <button disabled={busyId===contact.id} onClick={()=>setTag(contact,"interested",!interested)} className={"icon-btn "+(interested?"text-brand-600":"")} title={interested?"Remove interested":"Mark interested"}>
                        <CheckCircle className="h-4 w-4"/>
                      </button>
                      <button disabled={busyId===contact.id} onClick={()=>setTag(contact,"not_interested",!notInterested)} className={"icon-btn "+(notInterested?"text-danger-600":"")} title={notInterested?"Remove not interested":"Mark not interested"}>
                        <XCircle className="h-4 w-4"/>
                      </button>
                      <span className={"ml-1 text-[11px] "+(reply?"text-brand-600":"text-ink-400")}>{reply?"Follow-up due":"—"}</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function AutomationView({api}){

  const [status,setStatus]=useState(null);

  const [history,setHistory]=useState([]);

  const [busy,setBusy]=useState(false);

  const [error,setError]=useState(null);

  const [note,setNote]=useState(null);

  const load=useCallback(async()=>{

    try{

      const [s,h]=await Promise.all([api("/api/scheduling/status"),api("/api/scheduling/history?limit=10")]);

      setStatus(s);

      setHistory(Array.isArray(h?.history)?h.history:[]);

      setError(null);

    }catch(e){

      setError(e?.message||"Could not load automation status");

    }

  },[api]);

  useEffect(()=>{ load(); },[load]);

  const toggle=async(enabled)=>{

    setBusy(true);

    try{

      await api("/api/scheduling/autopilot",{method:"POST",body:JSON.stringify({enabled})});

      setNote(enabled?"Autopilot enabled":"Autopilot disabled");

      await load();

    }catch(e){

      setError(e?.message||"Could not change autopilot");

    }finally{

      setBusy(false);

    }

  };

  const runNow=async()=>{

    setBusy(true);

    try{

      const r=await api("/api/scheduling/run-now",{method:"POST"});

      const rr=r?.result||{};

      setNote(`Pass started: ${rr.intros_drafted||0} drafted, ${rr.replies_answered||0} replies answered. Sending continues in the background.`);

      await load();

      if(rr.job_id){

        for(let attempt=0;attempt<120;attempt+=1){

          await new Promise(resolve=>setTimeout(resolve,5000));

          try{

            const job=await api(`/api/queue/jobs/${rr.job_id}`);

            await load();

            if(job.status==="complete"||job.status==="failed"){

              const jr=job.result||{};

              setNote(job.status==="failed"?`Background send failed: ${job.error||"unknown error"}`:`Pass finished: ${jr.sent||0} sent, ${jr.failed||0} failed${jr.paused?" (stopped by a sending limit)":""}`);

              break;

            }

          }catch{break;}

        }

      }

    }catch(e){

      setError(e?.message||"Could not run a pass");

    }finally{

      setBusy(false);

    }

  };

  const jobs=status?.jobs||[];

  return (

    <div className="space-y-4">

      <PageHeader title="Automation" subtitle="Autopilot, scheduled jobs and recent scheduler activity." eyebrow="Operations">

        <button onClick={load} disabled={busy} className={btnGhost + " btn-sm"}>Refresh</button>

        <button onClick={runNow} disabled={busy} className={btnPrimary + " btn-sm"}>Run a pass now</button>

      </PageHeader>

      {error&&<ErrorDisplay err={error} onRetry={load}/>}

      {note&&<div className="notice-ok">{note}</div>}

      <div className="grid gap-4 lg:grid-cols-3">

        <Card title="Autopilot" className="lg:col-span-2">

          <div className="space-y-4">

            <div className="flex items-center justify-between gap-4">

              <div>

                <div className="text-[13.5px] font-semibold text-ink-900">Run the queue automatically</div>

                <div className="mt-0.5 text-[12px] text-ink-500">Drafts intros, answers replies and sends follow-ups on a timer, with no approval step.</div>

              </div>

              <button

                onClick={()=>toggle(!status?.autopilot_enabled)}

                disabled={busy||!status}

                className={status?.autopilot_enabled?btnGhost:btnPrimary}

              >

                {status?.autopilot_enabled?"Disable":"Enable"}

              </button>

            </div>

            <div className="divide-y divide-ink-100 text-[12.5px]">

              {[["Autopilot",status?.autopilot_enabled],["Auto-send",status?.auto_approve_enabled],["Follow-ups",status?.followups_enabled]].map(([label,on])=>(

                <div key={label} className="flex items-center justify-between py-2">

                  <span className="text-ink-600">{label}</span>

                  <span className={"badge "+(on?"badge-sent":"badge-draft")}>{on?"On":"Off"}</span>

                </div>

              ))}

            </div>

          </div>

        </Card>

        <Card title="Scheduled jobs">

          <div className="space-y-2">

            {jobs.length===0&&<div className="text-[12px] text-ink-500">No scheduled jobs reported.</div>}

            {jobs.map(job=>(

              <div key={job.id} className="flex items-center justify-between gap-3 border-b border-ink-100 pb-2 text-[13px] last:border-0 last:pb-0">

                <div className="min-w-0">

                  <div className="truncate font-medium text-ink-900">{job.label}</div>

                  <div className="text-[11.5px] text-ink-500">

                    {job.scheduled

                      ? (job.next_run?`Next run ${new Date(job.next_run).toLocaleString()}`:"Scheduled")

                      : "Not scheduled"}

                  </div>

                </div>

                <span className={"badge "+(job.scheduled?"badge-sent":"badge-draft")}>

                  {job.scheduled?"Active":"Inactive"}

                </span>

              </div>

            ))}

          </div>

        </Card>

      </div>

      <Card title="Recent activity">

        {history.length===0

          ? <div className="text-[12px] text-ink-500">No scheduler activity yet.</div>

          : <ul className="space-y-2 text-[13px]">

              {history.map((entry,i)=>(

                <li key={`${entry.timestamp}-${i}`} className="flex items-start justify-between gap-3 border-b border-ink-100 pb-2 last:border-0 last:pb-0">

                  <span className="text-ink-700">{entry.message}</span>

                  <span className="shrink-0 text-[11.5px] tabular-nums text-ink-400">{entry.timestamp?new Date(entry.timestamp).toLocaleString():"—"}</span>

                </li>

              ))}

            </ul>}

      </Card>

    </div>

  );

}



function TeamView({api,currentUserId}){

  const [members,setMembers]=useState([]);

  const [loading,setLoading]=useState(true);

  const [error,setError]=useState(null);

  const [note,setNote]=useState(null);

  const [inviteForm,setInviteForm]=useState({email:"",name:"",role:"member"});

  const [inviting,setInviting]=useState(false);

  const [busyId,setBusyId]=useState(null);

  const load=useCallback(async()=>{

    setLoading(true);

    try{

      const rows=await api("/api/tenants/members");

      setMembers(Array.isArray(rows)?rows:[]);

      setError(null);

    }catch(e){

      setError(e?.message||"Could not load team");

    }finally{

      setLoading(false);

    }

  },[api]);

  useEffect(()=>{ load(); },[load]);

  const invite=async(e)=>{

    e.preventDefault();

    if(!inviteForm.email.trim()) return;

    setInviting(true);

    setNote(null);

    try{

      const created=await api("/api/tenants/members",{method:"POST",body:JSON.stringify(inviteForm)});

      setNote(created?.temporary_password

        ? `Invited. Temporary password: ${created.temporary_password}`

        : "Member added.");

      setInviteForm({email:"",name:"",role:"member"});

      await load();

    }catch(err){

      setError(err?.message||"Could not invite that person");

    }finally{

      setInviting(false);

    }

  };

  const changeRole=async(memberId,role)=>{

    setBusyId(memberId);

    try{

      await api(`/api/tenants/members/${memberId}`,{method:"PATCH",body:JSON.stringify({role})});

      await load();

    }catch(e){

      setError(e?.message||"Could not change that role");

    }finally{

      setBusyId(null);

    }

  };

  const remove=async(memberId)=>{

    setBusyId(memberId);

    try{

      await api(`/api/tenants/members/${memberId}`,{method:"DELETE"});

      await load();

    }catch(e){

      setError(e?.message||"Could not remove that member");

    }finally{

      setBusyId(null);

    }

  };

  return (

    <div className="space-y-4">

      <PageHeader title="Team" subtitle="Invite teammates and manage who can access this workspace." eyebrow="Workspace">

        <button onClick={load} disabled={loading} className={btnGhost + " btn-sm"}>Refresh</button>

      </PageHeader>

      {error&&<ErrorDisplay err={error} onRetry={load}/>}

      {note&&<div className="notice-ok break-all">{note}</div>}

      <Card title="Invite a teammate">

        <form onSubmit={invite} className="flex flex-wrap items-end gap-2">

          <div className="min-w-[200px] flex-1">

            <label className="field-label mb-1 block">Email</label>

            <input

              type="email"

              required

              className={inputCls}

              value={inviteForm.email}

              onChange={e=>setInviteForm({...inviteForm,email:e.target.value})}

              placeholder="teammate@company.com"

            />

          </div>

          <div className="w-40">

            <label className="field-label mb-1 block">Name</label>

            <input

              className={inputCls}

              value={inviteForm.name}

              onChange={e=>setInviteForm({...inviteForm,name:e.target.value})}

              placeholder="Optional"

            />

          </div>

          <div className="w-32">

            <label className="field-label mb-1 block">Role</label>

            <select

              className={inputCls}

              value={inviteForm.role}

              onChange={e=>setInviteForm({...inviteForm,role:e.target.value})}

            >

              <option value="member">Member</option>

              <option value="admin">Admin</option>

            </select>

          </div>

          <button type="submit" disabled={inviting} className={btnPrimary}>

            {inviting?"Inviting...":"Invite"}

          </button>

        </form>

      </Card>

      <Card title={`Members (${members.length})`}>

        {loading

          ? <div className="flex items-center gap-2 text-[12px] text-ink-500"><Loader2 className="h-3.5 w-3.5 animate-spin"/>Loading...</div>

          : <ul className="divide-y divide-ink-100">

              {members.map(m=>(

                <li key={m.id} className="flex items-center justify-between gap-3 py-2.5">

                  <div className="min-w-0">

                    <div className="truncate text-[13.5px] font-medium text-ink-900">{m.name||m.email}</div>

                    <div className="truncate text-[12px] text-ink-500">{m.email}</div>

                  </div>

                  <div className="flex shrink-0 items-center gap-2">

                    <select

                      className="select py-1 text-[12px]"

                      value={m.role}

                      disabled={busyId===m.id}

                      onChange={e=>changeRole(m.id,e.target.value)}

                    >

                      <option value="admin">Admin</option>

                      <option value="member">Member</option>

                    </select>

                    <button

                      onClick={()=>remove(m.id)}

                      disabled={busyId===m.id||m.user_id===currentUserId}

                      className="icon-btn hover:text-danger-600"

                      title={m.user_id===currentUserId?"You cannot remove yourself":"Remove member"}

                    >

                      <Trash2 className="h-4 w-4"/>

                    </button>

                  </div>

                </li>

              ))}

            </ul>}

      </Card>

    </div>

  );

}



function ExperimentsView({api}){

  const [tests,setTests]=useState([]);

  const [results,setResults]=useState([]);

  const [templates,setTemplates]=useState([]);

  const [loading,setLoading]=useState(true);

  const [busy,setBusy]=useState(false);

  const [error,setError]=useState(null);

  const [note,setNote]=useState(null);

  const [form,setForm]=useState({

    name:"",

    template_id:"",

    variantA:{label:"control",subject:"",body:""},

    variantB:{label:"challenger",subject:"",body:""},

  });

  const load=useCallback(async()=>{

    setLoading(true);

    try{

      const [t,r,tpl]=await Promise.all([

        api("/api/ab-tests"),

        api("/api/ab-tests/results"),

        api("/api/templates"),

      ]);

      setTests(Array.isArray(t)?t:[]);

      setResults(Array.isArray(r)?r:[]);

      setTemplates(Array.isArray(tpl?.templates)?tpl.templates:[]);

      setError(null);

    }catch(e){

      setError(e?.message||"Could not load experiments");

    }finally{

      setLoading(false);

    }

  },[api]);

  useEffect(()=>{ load(); },[load]);

  const create=async()=>{

    setBusy(true);

    setError(null);

    try{

      await api("/api/ab-tests",{method:"POST",body:JSON.stringify({

        name:form.name||"Untitled experiment",

        template_id:form.template_id?Number(form.template_id):null,

        variants:[form.variantA,form.variantB],

      })});

      setNote("Experiment created");

      setForm({name:"",template_id:"",variantA:{label:"control",subject:"",body:""},variantB:{label:"challenger",subject:"",body:""}});

      await load();

    }catch(e){

      setError(e?.message||"Could not create the experiment");

    }finally{

      setBusy(false);

    }

  };

  const setStatus=async(test,status)=>{

    setBusy(true);

    try{

      await api(`/api/ab-tests/${test.id}`,{method:"PATCH",body:JSON.stringify({status})});

      await load();

    }catch(e){

      setError(e?.message||"Could not update the experiment");

    }finally{

      setBusy(false);

    }

  };

  const remove=async(test)=>{

    setBusy(true);

    try{

      await api(`/api/ab-tests/${test.id}`,{method:"DELETE"});

      await load();

    }catch(e){

      setError(e?.message||"Could not delete the experiment");

    }finally{

      setBusy(false);

    }

  };

  const resultsFor=(id)=>results.find(r=>r.test_id===id);

  const canCreate=form.name.trim()&&form.variantA.subject.trim()&&form.variantB.subject.trim();

  return (

    <div className="space-y-4">

      <PageHeader title="Experiments" subtitle="Test subject lines and bodies. Each contact is assigned by a stable hash of its id." eyebrow="Campaigns">

        <button onClick={load} disabled={loading||busy} className={btnGhost + " btn-sm"}>Refresh</button>

      </PageHeader>

      {error&&<ErrorDisplay err={error} onRetry={load}/>}

      {note&&<div className="notice-ok">{note}</div>}

      <Card title="New A/B test" subtitle="Two variants, split evenly across your audience.">

        <div className="space-y-3">

          <div className="grid gap-3 sm:grid-cols-2">

            <div>

              <label className="field-label mb-1 block">Experiment name</label>

              <input type="text" placeholder="e.g. Subject line test" className={inputCls} value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))}/>

            </div>

            <div>

              <label className="field-label mb-1 block">Template</label>

              <select className="select w-full" value={form.template_id} onChange={e=>setForm(f=>({...f,template_id:e.target.value}))}>

                <option value="">Any active template</option>

                {templates.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}

              </select>

            </div>

          </div>

          <div className="grid gap-3 sm:grid-cols-2">

            {[["variantA","A"],["variantB","B"]].map(([key,letter])=>(

              <div key={key} className="space-y-2 rounded-lg border border-ink-200 bg-ink-50/60 p-3">

                <div className="badge badge-sent">Variant {letter}</div>

                <input type="text" placeholder="Label" className={inputCls} value={form[key].label} onChange={e=>setForm(f=>({...f,[key]:{...f[key],label:e.target.value}}))}/>

                <input type="text" placeholder="Subject line" className={inputCls} value={form[key].subject} onChange={e=>setForm(f=>({...f,[key]:{...f[key],subject:e.target.value}}))}/>

                <textarea placeholder="Body" rows={3} className={inputCls + " resize-y"} value={form[key].body} onChange={e=>setForm(f=>({...f,[key]:{...f[key],body:e.target.value}}))}/>

              </div>

            ))}

          </div>

          <button onClick={create} disabled={busy||!canCreate} className={btnPrimary}>Create experiment</button>

          <p className="text-[12px] text-ink-500">
            Each contact is assigned to one variant by a stable hash of its id, so the same
            contact always receives the same message.
          </p>

        </div>

      </Card>

      <Card title="Experiments">

        {loading

          ? <div className="flex items-center gap-2 text-[12px] text-ink-500"><Loader2 className="h-3.5 w-3.5 animate-spin"/>Loading…</div>

          : tests.length===0

            ? <EmptyState icon={Sparkles} title="No experiments yet" description="Create your first A/B test to compare subject lines."/>

            : <div className="space-y-3">

                {tests.map(test=>{

                  const stats=resultsFor(test.id);

                  return (

                    <div key={test.id} className="space-y-3 rounded-lg border border-ink-200 p-3.5">

                      <div className="flex items-center justify-between gap-3">

                        <div className="min-w-0">

                          <div className="truncate text-[13.5px] font-semibold text-ink-900">{test.name}</div>

                          <div className="text-[12px] text-ink-500">
                            {test.variants.length} variant{test.variants.length===1?"":"s"} · <StatusPill status={test.status}/>
                          </div>

                        </div>

                        <div className="flex shrink-0 items-center gap-2">

                          <button onClick={()=>setStatus(test,test.status==="active"?"paused":"active")} disabled={busy} className={btnGhost + " btn-sm"}>

                            {test.status==="active"?"Pause":"Resume"}

                          </button>

                          <button onClick={()=>remove(test)} disabled={busy} className="icon-btn hover:text-danger-600" title="Delete experiment">

                            <Trash2 className="h-4 w-4"/>

                          </button>

                        </div>

                      </div>

                      <div className="-mx-3.5 overflow-x-auto">

                        <table className="data-table">

                          <thead>

                            <tr>

                              <th>Variant</th>

                              <th className="text-right">Sent</th>

                              <th className="text-right">Opened</th>

                              <th className="text-right">Clicked</th>

                              <th className="text-right">Replied</th>

                              <th className="text-right">Reply rate</th>

                            </tr>

                          </thead>

                          <tbody>

                            {(stats?.variants||test.variants.map(v=>({...v,sent:0,opened:0,clicked:0,replied:0,reply_rate:0}))).map(v=>(

                              <tr key={v.variant_id||v.id}>

                                <td className="font-medium text-ink-900">{v.label}</td>

                                <td className="text-right tabular-nums">{v.sent}</td>

                                <td className="text-right tabular-nums">{v.opened}</td>

                                <td className="text-right tabular-nums">{v.clicked}</td>

                                <td className="text-right tabular-nums">{v.replied}</td>

                                <td className="text-right font-medium tabular-nums text-ink-900">{v.reply_rate}%</td>

                              </tr>

                            ))}

                          </tbody>

                        </table>

                      </div>

                      <p className="text-[11.5px] text-ink-500">
                        Opened and clicked require engagement tracking to be enabled in Settings.
                      </p>

                    </div>

                  );

                })}

              </div>}

      </Card>

    </div>

  );

}



export default function App(){

  const [user,setUser]=useState(null);

  const [view,setView]=useState(()=>{
    const path=window.location.pathname.replace(/^\/+|\/+$/g,"");
    return KNOWN_VIEWS.includes(path)?path:"overview";
  });

  const [navOpen,setNavOpen]=useState(false);

  // Hold the opening wordmark briefly so it is actually seen, then reveal.
  const [splashDone,setSplashDone]=useState(false);

  const [state,setState]=useState({contacts:[],drafts:[],events:[],logs:[],tools:[],analytics:{}});

  const analytics=state.analytics||{};

  const usage=state.usage||{};

  const [smtp,setSmtp]=useState({host:"",port:"",user:"",pass:"",sender:""});

  const [smtpConfig,setSmtpConfig]=useState(null);

  const [smtpCheck,setSmtpCheck]=useState(null);

  const [smtpDirty,setSmtpDirty]=useState(false);

  const [smtpError,setSmtpError]=useState(null);

  const [imap,setImap]=useState({host:"",port:"",user:"",pass:"",folder:"INBOX"});

  const [imapConfig,setImapConfig]=useState(null);

  const [imapCheck,setImapCheck]=useState(null);

  const [imapDirty,setImapDirty]=useState(false);

  const [imapError,setImapError]=useState(null);

  const [draftError,setDraftError]=useState(null);

  const [health,setHealth]=useState(null);

  const [sendingDraftId,setSendingDraftId]=useState(null);

  const [status,setStatus]=useState(null);

  const [loading,setLoading]=useState(true);

  const [error,setError]=useState(null);

  // live system status + authoring features

  const [sys,setSys]=useState(null);

  const [csvBusy,setCsvBusy]=useState(false);

  const [composing,setComposing]=useState(false);

  const [composeForm,setComposeForm]=useState({contact_id:"",subject:"",body:""});

  const [editingId,setEditingId]=useState(null);

  const [editForm,setEditForm]=useState({subject:"",body:""});

  const [redraftingId,setRedraftingId]=useState(null);

  const [eligibilityBusyId,setEligibilityBusyId]=useState(null);

  const [settingsForm,setSettingsForm]=useState({goal:"",business_name:"",business_offer:"",tracking_enabled:false});

  const [settingsDirty,setSettingsDirty]=useState(false);

  const [savingSettings,setSavingSettings]=useState(false);

  const fileInputRef=useRef(null);

  

  // Verifications state

  const [verifications, setVerifications] = useState([]);

  const [verificationStats, setVerificationStats] = useState({total:0,deliverable:0,undeliverable:0,risky:0,inconclusive:0,not_checked:0});

  const [verificationLoading, setVerificationLoading] = useState(false);

  const [verifyModalOpen, setVerifyModalOpen] = useState(false);

  const [verifyJob, setVerifyJob] = useState(null);

  const [verifyProgress, setVerifyProgress] = useState({processed:0,total:0,deliverable:0,undeliverable:0,risky:0,inconclusive:0});

  const [verifyFilter, setVerifyFilter] = useState("all");

  const [verifySearch, setVerifySearch] = useState("");

  const [contactsSearch, setContactsSearch] = useState("");

  const [selectedContacts, setSelectedContacts] = useState(new Set());

  const [selectAllContacts, setSelectAllContacts] = useState(false);

  // Confirmation dialog (replaces window.confirm so destructive actions match the app)
  const [confirmState, setConfirmState] = useState(null);

  const confirmAction = ({title, message, confirmLabel="Delete", tone="danger", onConfirm}) =>
    setConfirmState({ title, message, confirmLabel, tone, onConfirm });



  // Lists/Segments state

  const [selectedList, setSelectedList] = useState("all");

  const [showListModal, setShowListModal] = useState(false);

  const [newListName, setNewListName] = useState("");

  const [newListFolder, setNewListFolder] = useState("");

  const [lists, setLists] = useState([]);

  const [listsLoading, setListsLoading] = useState(false);

  const [listError, setListError] = useState(null);

  const [listContacts, setListContacts] = useState({});

  // Brevo folders group lists, so the page keeps them alongside the lists.
  const [folders, setFolders] = useState([]);

  const [folderFilter, setFolderFilter] = useState("all");

  const [showFolderModal, setShowFolderModal] = useState(false);

  const [newFolderName, setNewFolderName] = useState("");

  const [folderError, setFolderError] = useState(null);

  const [openListMenu, setOpenListMenu] = useState(null);

  const [listSearch, setListSearch] = useState("");

  const [showListSettings, setShowListSettings] = useState(null);

  const [listSettingsForm, setListSettingsForm] = useState({description:"",from_name:"",from_email:"",reply_to:"",header:"",footer:""});

  const [showRenameList, setShowRenameList] = useState(null);

  const [renameListName, setRenameListName] = useState("");

  const [showMoveList, setShowMoveList] = useState(null);

  const [showAddToList, setShowAddToList] = useState(null);

  const [addToListIds, setAddToListIds] = useState([]);

  const [listBusy, setListBusy] = useState(false);

  const [listNotice, setListNotice] = useState(null);

  const [showListImport, setShowListImport] = useState(null);

  const [listImportText, setListImportText] = useState("");

  const flashList = (message) => {

    setListNotice(message);

    setTimeout(() => setListNotice(null), 3000);

  };

  const createList = async () => {

    const name = newListName.trim();

    if (!name) return;

    try {

      const created = await api("/api/lists", {

        method: "POST",

        body: JSON.stringify({

          name,

          folderId: newListFolder ? Number(newListFolder) : undefined,

        }),

      });

      setNewListName("");

      setNewListFolder("");

      setShowListModal(false);

      // Brevo puts a newly created list at the top of the list row and opens
      // it, so prepend it instead of waiting for an alphabetical reload.
      if (created && created.id) {

        setLists(prev => [created, ...prev.filter(l => l.id !== created.id)]);

        setListContacts(prev => ({ ...prev, [String(created.id)]: [] }));

        setSelectedList(String(created.id));

        flashList(`List "${created.name}" created`);

      }

      await Promise.all([loadLists(), loadFolders()]);

    } catch (e) {

      setListError(e?.message || "Could not create list");

    }

  };

  const createFolder = async () => {

    const name = newFolderName.trim();

    if (!name) return;

    try {

      await api("/api/lists/folders", { method: "POST", body: JSON.stringify({ name }) });

      setNewFolderName("");

      setShowFolderModal(false);

      await loadFolders();

      flashList(`Folder "${name}" created`);

    } catch (e) {

      setFolderError(e?.message || "Could not create folder");

    }

  };

  const renameList = async (listId, name) => {

    const trimmed = (name || "").trim();

    if (!trimmed) return;

    try {

      const updated = await api(`/api/lists/${listId}`, {

        method: "PUT",

        body: JSON.stringify({ name: trimmed }),

      });

      setLists(prev => prev.map(l => (l.id === listId ? updated : l)));

      setShowRenameList(null);

      flashList("List renamed");

    } catch (e) {

      setListError(e?.message || "Could not rename list");

    }

  };

  const moveList = async (listId, folderId) => {

    try {

      const updated = await api(`/api/lists/${listId}`, {

        method: "PUT",

        body: JSON.stringify({ folderId: folderId === "none" ? null : Number(folderId) }),

      });

      setLists(prev => prev.map(l => (l.id === listId ? updated : l)));

      setShowMoveList(null);

      await loadFolders();

      flashList("List moved");

    } catch (e) {

      setListError(e?.message || "Could not move list");

    }

  };

  const duplicateList = async (listId) => {

    try {

      const copy = await api(`/api/lists/${listId}/duplicate`, { method: "POST", body: JSON.stringify({}) });

      setLists(prev => [copy, ...prev]);

      setListContacts(prev => ({ ...prev, [String(copy.id)]: [] }));

      await loadFolders();

      flashList(`Duplicated as "${copy.name}"`);

    } catch (e) {

      setListError(e?.message || "Could not duplicate list");

    }

  };

  const saveListSettings = async () => {

    if (!showListSettings) return;

    setListBusy(true);

    try {

      const updated = await api(`/api/lists/${showListSettings.id}/settings`, {

        method: "PUT",

        body: JSON.stringify(listSettingsForm),

      });

      setLists(prev => prev.map(l => (l.id === updated.id ? updated : l)));

      setShowListSettings(null);

      flashList("List settings saved");

    } catch (e) {

      setListError(e?.message || "Could not save list settings");

    } finally {

      setListBusy(false);

    }

  };

  const cleanupListMembers = async (listId, action) => {

    setListBusy(true);

    try {

      const result = await api(`/api/lists/${listId}/contacts/${action}`, { method: "POST" });

      await Promise.all([loadLists(), loadListMembers(listId)]);

      flashList(action === "remove-duplicates" ? `Removed ${result.removed} duplicate contact(s)` : `Removed ${result.removed} contact(s) from other lists`);

    } catch (e) {

      setListError(e?.message || "Could not update contacts");

    } finally {

      setListBusy(false);

    }

  };

  const importCsvToList = async () => {

    if (!showListImport || !listImportText.trim()) return;

    setListBusy(true);

    try {

      const result = await api(`/api/lists/${showListImport.id}/import`, {

        method: "POST",

        body: JSON.stringify({ csv: listImportText }),

      });

      setShowListImport(null);

      setListImportText("");

      await Promise.all([load(), loadLists(), loadListMembers(showListImport.id)]);

      flashList(`Imported ${result.imported} contact(s) into ${showListImport.name}`);

    } catch (e) {

      setListError(e?.message || "Could not import contacts");

    } finally {

      setListBusy(false);

    }

  };

  const addSelectedContactsToList = async () => {

    if (!showAddToList || !addToListIds.length) return;

    setListBusy(true);

    try {

      const result = await api(`/api/lists/${showAddToList.id}/contacts/add`, {

        method: "POST",

        body: JSON.stringify({ ids: addToListIds.map(Number) }),

      });

      setShowAddToList(null);

      setAddToListIds([]);

      await Promise.all([loadLists(), loadListMembers(showAddToList.id)]);

      flashList(`Added ${result.total} contact(s) to ${showAddToList.name}`);

    } catch (e) {

      setListError(e?.message || "Could not add contacts");

    } finally {

      setListBusy(false);

    }

  };

  const deleteList = async (listId) => {

    const target = lists.find(l => String(l.id) === String(listId));

    confirmAction({
      title: `Delete the list "${target?.name || listId}"?`,
      message: "Contacts stay in your account; they are only removed from this list.",
      onConfirm: async () => {
        try {

          await api(`/api/lists/${listId}`, { method: "DELETE" });

          if (selectedList === String(listId)) setSelectedList("all");

          setLists(prev => prev.filter(l => String(l.id) !== String(listId)));

          await Promise.all([loadLists(), loadFolders()]);

          flashList("List deleted");

        } catch (e) {

          setListError(e?.message || "Could not delete list");

        }
      },
    });

  };

  const addContactsToList = async (listId, contactIds) => {

    if (!contactIds.length) return;

    try {

      await api(`/api/lists/${listId}/contacts/add`, {

        method: "POST",

        body: JSON.stringify({ ids: contactIds.map(Number) }),

      });

      await Promise.all([loadLists(), loadListMembers(listId)]);

      const target = lists.find(l => String(l.id) === String(listId));

      flashList(`Added ${contactIds.length} contact(s) to ${target?.name || "list"}`);

    } catch (e) {

      setListError(e?.message || "Could not add contacts to list");

    }

  };

  const removeContactFromList = async (listId, contactId) => {

    try {

      await api(`/api/lists/${listId}/contacts/${contactId}`, { method: "DELETE" });

      await Promise.all([loadLists(), loadListMembers(listId)]);

      flashList("Contact removed from list");

    } catch (e) {

      setListError(e?.message || "Could not remove contact from list");

    }

  };

  // ---------------------------------------------------------------- campaigns
  // Brevo's Campaigns page: a listing of sends with a channel picker, status
  // filters and per-campaign results. Creating one opens a small editor that
  // picks a list and a template, as in the Brevo reference screen.
  const [campaigns, setCampaigns] = useState([]);

  const [campaignsLoading, setCampaignsLoading] = useState(false);

  const [campaignError, setCampaignError] = useState(null);

  const [campaignNotice, setCampaignNotice] = useState(null);

  const [campaignSearch, setCampaignSearch] = useState("");

  const [campaignStatusFilter, setCampaignStatusFilter] = useState("all");

  const [campaignChannel, setCampaignChannel] = useState("email");

  const [showCampaignModal, setShowCampaignModal] = useState(false);

  const [campaignForm, setCampaignForm] = useState({ name: "", subject: "", preview_text: "", channel: "email", template_id: "", list_id: "", scheduled_at: "" });

  const [campaignBusy, setCampaignBusy] = useState(false);

  const [campaignDetail, setCampaignDetail] = useState(null);

  const [openCampaignMenu, setOpenCampaignMenu] = useState(null);

  const flashCampaign = (message) => {

    setCampaignNotice(message);

    setTimeout(() => setCampaignNotice(null), 3500);

  };

  const loadCampaigns = useCallback(async () => {

    setCampaignsLoading(true);

    try {

      const rows = await api("/api/campaigns?sort=desc");

      setCampaigns(Array.isArray(rows) ? rows : []);

      setCampaignError(null);

    } catch (e) {

      setCampaignError(e?.message || "Could not load campaigns");

    } finally {

      setCampaignsLoading(false);

    }

  }, []);

  const openCampaignEditor = () => {

    setCampaignForm({

      name: "",

      subject: "",

      preview_text: "",

      channel: campaignChannel,

      template_id: templates[0] ? String(templates[0].id) : "",

      list_id: lists[0] ? String(lists[0].id) : "",

      scheduled_at: "",

    });

    setCampaignError(null);

    setShowCampaignModal(true);

  };

  const createCampaign = async () => {

    const name = campaignForm.name.trim();

    if (!name) { setCampaignError("Give the campaign a name"); return; }

    setCampaignBusy(true);

    try {

      const created = await api("/api/campaigns", {

        method: "POST",

        body: JSON.stringify({

          name,

          subject: campaignForm.subject.trim() || undefined,

          preview_text: campaignForm.preview_text.trim() || undefined,

          channel: campaignForm.channel,

          template_id: campaignForm.template_id ? Number(campaignForm.template_id) : undefined,

          list_id: campaignForm.list_id ? Number(campaignForm.list_id) : undefined,

          scheduled_at: campaignForm.scheduled_at || undefined,

        }),

      });

      setCampaigns(prev => [created, ...prev.filter(c => c.id !== created.id)]);

      setShowCampaignModal(false);

      flashCampaign(`Campaign "${created.name}" created`);

    } catch (e) {

      setCampaignError(e?.message || "Could not create campaign");

    } finally {

      setCampaignBusy(false);

    }

  };

  const sendCampaign = async (campaign) => {

    confirmAction({
      title: `Send "${campaign.name}"?`,
      message: `This queues and sends real email to ${campaign.total_recipients || 0} recipient(s). Sending limits and pacing still apply.`,
      confirmLabel: "Send campaign",
      onConfirm: async () => {
        setCampaignBusy(true);

        setCampaignError(null);

        try {

          const result = await api("/api/queue/run-all", {

            method: "POST",

            body: JSON.stringify({ campaign_id: campaign.id }),

          });

          await Promise.all([load(), loadCampaigns()]);

          flashCampaign(
            result.queued
              ? `Campaign queued: ${result.result?.sent ?? 0} delivered so far, sending continues in the background`
              : `Campaign sent: ${result.result?.sent ?? 0} delivered, ${result.drafts_created ?? 0} drafted`
          );

        } catch (e) {

          setCampaignError(e?.message || "Could not send campaign");

        } finally {

          setCampaignBusy(false);

        }
      },
    });

  };

  const duplicateCampaign = async (campaignId) => {

    try {

      const copy = await api(`/api/campaigns/${campaignId}/duplicate`, { method: "POST", body: JSON.stringify({}) });

      setCampaigns(prev => [copy, ...prev]);

      flashCampaign(`Duplicated as "${copy.name}"`);

    } catch (e) {

      setCampaignError(e?.message || "Could not duplicate campaign");

    }

  };

  const setCampaignState = async (campaignId, action) => {

    try {

      const updated = await api(`/api/campaigns/${campaignId}/${action}`, { method: "POST", body: JSON.stringify({}) });

      setCampaigns(prev => prev.map(c => (c.id === updated.id ? updated : c)));

      flashCampaign(`${updated.name} ${action === "pause" ? "paused" : "cancelled"}`);

    } catch (e) {

      setCampaignError(e?.message || `Could not ${action} campaign`);

    }

  };

  const deleteCampaign = async (campaignId) => {

    const target = campaigns.find(c => c.id === campaignId);

    confirmAction({
      title: `Delete the campaign "${target?.name || campaignId}"?`,
      message: "Recipients, drafts and results for this campaign are removed. Contacts are not affected.",
      onConfirm: async () => {
        try {

          await api(`/api/campaigns/${campaignId}`, { method: "DELETE" });

          setCampaigns(prev => prev.filter(c => c.id !== campaignId));

          flashCampaign("Campaign deleted");

        } catch (e) {

          setCampaignError(e?.message || "Could not delete campaign");

        }
      },
    });

  };

  const openCampaignDetail = async (campaign) => {

    try {

      const detail = await api(`/api/campaigns/${campaign.id}/stats`);

      setCampaignDetail(detail);

    } catch (e) {

      setCampaignError(e?.message || "Could not load campaign stats");

    }

  };

  // Filter contacts by list/segment (must come after selectedList and lists)

  const filteredContacts = state.contacts?.filter(c => {

    if (selectedList === "eligible") {

      if (c.eligible_to_email !== true) return false;

    } else if (selectedList !== "all") {

      const memberIds = listContacts[selectedList];

      // A list whose members have not loaded yet must show nothing rather
      // than fall through to every contact in the account.
      if (!Array.isArray(memberIds)) return false;

      if (!memberIds.includes(c.id)) return false;

    }

    const term = contactsSearch.trim().toLowerCase();

    if (!term) return true;

    return (c.email || "").toLowerCase().includes(term)
      || (c.name || "").toLowerCase().includes(term)
      || (c.company || "").toLowerCase().includes(term);

  }) || [];

  const filteredContactsCount = filteredContacts.length;

  // Brevo shows lists newest-first and lets you narrow by folder or search.
  const visibleLists = lists.filter(list => {

    if (folderFilter === "none" && list.folder_id) return false;

    if (folderFilter !== "all" && folderFilter !== "none" && String(list.folder_id || "") !== String(folderFilter)) return false;

    const term = listSearch.trim().toLowerCase();

    if (!term) return true;

    return (list.name || "").toLowerCase().includes(term);

  });

  // The campaigns listing honours the same search + status filters as Brevo.
  const visibleCampaigns = campaigns.filter(campaign => {

    if (campaignChannel && campaign.channel && campaign.channel !== campaignChannel) return false;

    if (campaignStatusFilter !== "all" && campaign.status !== campaignStatusFilter) return false;

    const term = campaignSearch.trim().toLowerCase();

    if (!term) return true;

    return (campaign.name || "").toLowerCase().includes(term) || (campaign.subject || "").toLowerCase().includes(term);

  });



  // Add Contact state

  const [addContactOpen, setAddContactOpen] = useState(false);

  const [addContactForm, setAddContactForm] = useState({email:"",name:"",company:"",role:"",industry:"",notes:"",eligible_to_email:true});

  const [sendSelectedOpen, setSendSelectedOpen] = useState(false);

  const [sendSelectedTemplate, setSendSelectedTemplate] = useState(null);

  const [sendSelectedSmtpReady, setSendSelectedSmtpReady] = useState(false);



  // Run orchestrator (manual trigger)

  const run = async () => {

    try {

      const result = await api("/api/run", {

        method: "POST",

        body: JSON.stringify({ goal: settingsForm.goal || undefined })

      });

      const r = result.result || {};

      setStatus(`Autopilot started: ${r.intros_drafted || 0} drafted, ${r.replies_answered || 0} replies answered. Sending continues in the background.`);

      setTimeout(() => setStatus(null), 6000);

      await load();

      // Sending is paced (one email per 60s), so the pass finishes server-side.
      // Poll briefly so the counters settle without the user pressing Run again.
      if (result.job_id) watchRunJob(result.job_id);

    } catch (e) {

      setError(e?.message || String(e));

    }

  };



  // Follow the background send job so the UI updates as paced mail goes out.
  // Stops as soon as the job finishes or the page is closed.
  const watchRunJob = async (jobId) => {

    for (let attempt = 0; attempt < 120; attempt += 1) {

      await new Promise(resolve => setTimeout(resolve, 5000));

      try {

        const job = await api(`/api/queue/jobs/${jobId}`);

        await load();

        if (job.status === "complete" || job.status === "failed") {

          const jobResult = job.result || {};

          setStatus(
            job.status === "failed"
              ? `Background send failed: ${job.error || "unknown error"}`
              : `Autopilot finished: ${jobResult.sent || 0} sent, ${jobResult.failed || 0} failed${jobResult.paused ? " (stopped by a sending limit)" : ""}`
          );

          setTimeout(() => setStatus(null), 6000);

          return;

        }

      } catch {

        return;

      }

    }

  };



  const loadLists = useCallback(async () => {

    setListsLoading(true);

    try {

      const rows = await api("/api/lists?sort=desc");

      setLists(Array.isArray(rows) ? rows : []);

      setListError(null);

    } catch (e) {

      setListError(e?.message || "Could not load lists");

    } finally {

      setListsLoading(false);

    }

  }, []);

  const loadFolders = useCallback(async () => {

    try {

      const data = await api("/api/lists/folders");

      setFolders(Array.isArray(data?.folders) ? data.folders : []);

    } catch (e) {

    }

  }, []);

  const loadListMembers = useCallback(async (listId) => {

    try {

      const rows = await api(`/api/lists/${listId}/contacts`);

      setListContacts(prev => ({ ...prev, [listId]: Array.isArray(rows) ? rows.map(c => c.id) : [] }));

    } catch (e) {

      setListError(e?.message || "Could not load list members");

    }

  }, []);

  // Keep the address bar in sync so a refresh or a shared deep link reopens
  // the same view, and the browser's back button moves between views.
  useEffect(()=>{

    const target=view==="overview"?"/":`/${view}`;

    if(window.location.pathname!==target){

      window.history.pushState({view}, "", target);

    }

  },[view]);

  useEffect(()=>{

    const onPop=(event)=>{

      const path=window.location.pathname.replace(/^\/+|\/+$/g,"");

      setView(KNOWN_VIEWS.includes(path)?path:"overview");

    };

    window.addEventListener("popstate", onPop);

    return ()=>window.removeEventListener("popstate", onPop);

  },[]);

  // The mobile drawer is an overlay: dismiss it on navigation, on Escape, and
  // freeze the page behind it so background content does not scroll.
  useEffect(()=>{

    if(!navOpen) return;

    const onKey=(event)=>{ if(event.key==="Escape") setNavOpen(false); };

    const previousOverflow=document.body.style.overflow;

    document.body.style.overflow="hidden";

    window.addEventListener("keydown", onKey);

    return ()=>{
      document.body.style.overflow=previousOverflow;
      window.removeEventListener("keydown", onKey);
    };

  },[navOpen]);

  useEffect(()=>{ setNavOpen(false); },[view]);

  // Resolve the workspace identity once on first load. The server serves every
  // request as its single implicit tenant, so this cannot fail with a 401 and
  // there is no sign-in screen to fall back to.
  useEffect(()=>{

    let active=true;
    (async()=>{

      try{

        const me=await api("/api/auth/me");

        if(active) setUser(me);

      }catch(err){

        if(active) setError(err?.message||String(err));

      }

    })();

    return ()=>{active=false;};

  },[]);

  useEffect(() => {

    if (!user) return;

    loadLists();

    loadFolders();

  }, [user, loadLists, loadFolders]);

  useEffect(() => {

    if (selectedList === "all" || selectedList === "eligible") return;

    loadListMembers(selectedList);

  }, [selectedList, loadListMembers]);

  const load=useCallback(async({quiet=false,signal}={})=>{

    try{

      const s=await api("/api/state",{signal});

      setState(normalizeState(s));

      setError(null);

    }catch(e){

      if(!quiet&&e?.name!=="AbortError")setError(e?.message||String(e));

    }finally{

      if(!quiet)setLoading(false);

    }

  },[]);

  useEffect(()=>{

    if(!user) return undefined;

    let active=true;

    const controller=new AbortController();

    const fetchState=async(quiet=false)=>{

      try{

        const s=await api("/api/state",{signal:controller.signal});

        if(active){setState(normalizeState(s));setError(null);}

      }catch(e){

        if(!active||e?.name==="AbortError")return;

          if(!quiet)setError(e?.message||String(e));

      }finally{

        if(active&&!quiet)setLoading(false);

      }

    };

    const fetchSys=async()=>{

      try{ if(active) setSys(await api("/api/queue/status")); }catch{ if(active) setSys(null); }

    };

    fetchState();

    fetchSys();

    const t=setInterval(()=>{fetchState(true);fetchSys();},10000);

    return ()=>{active=false;clearInterval(t);controller.abort();};

  },[user]);



  // Template state

  const [templates, setTemplates] = useState([]);

  const [templateCategories, setTemplateCategories] = useState([]);

  const [templateLoading, setTemplateLoading] = useState(false);

  const [templateDraftError, setTemplateDraftError] = useState(null);

  const [templateForm, setTemplateForm] = useState({

    name: "", category: "intro", subject_template: "", body_template: "",

    variables: {}, tags: [], is_active: true

  });

  const [editingTemplate, setEditingTemplate] = useState(null);

  const [templateComposer, setTemplateComposer] = useState(false);

  const [templateError, setTemplateError] = useState(null);



  // Load templates

  const loadTemplates = useCallback(async () => {

    try {

      const cats = await api("/api/templates/categories");

      setTemplateCategories(cats.categories);

      const t = await api("/api/templates");

      const tList = Array.isArray(t?.templates) ? t.templates : [];

      setTemplates(tList);

    } catch (e) {

      console.error("Failed to load templates:", e);

    }

  }, []);



  useEffect(() => {

    if (!user) return;

    loadTemplates();

  }, [user]);



  // Use template

  const useTemplate = async (templateId, contactId, customValues = {}) => {

    try {

      const result = await api("/api/templates/use", {

        method: "POST",        body: JSON.stringify({ template_id: templateId, contact_id: contactId, custom_values: customValues, auto_approve: false, send_via_smtp: false })

      });

      return result;

    } catch (e) {

      throw e;

    }

  };



  // Expand template

  const expandTemplate = async (templateId, contactId, customValues = {}) => {

    try {

      return await api("/api/templates/expand", {

        method: "POST",

        body: JSON.stringify({

          template_id: templateId,

          contact_id: contactId,

          custom_values: customValues

        })

      });

    } catch (e) {

      throw e;

    }

  };



  // Create template

  const createTemplate = async () => {

    const result = await api("/api/templates", {

      method: "POST",

      body: JSON.stringify(templateForm)

    });

    await loadTemplates();

    return result;

  };



  // Open the template editor, pre-filled when editing an existing template.

  const openTemplateComposer = (template) => {

    setEditingTemplate(template || null);

    setTemplateError(null);

    setTemplateForm(template ? {

      name: template.name || "",

      category: template.category || "intro",

      subject_template: template.subject_template || "",

      body_template: template.body_template || "",

      variables: template.variables || {},

      tags: template.tags || [],

      is_active: template.is_active !== false,

    } : { name: "", category: "intro", subject_template: "", body_template: "", variables: {}, tags: [], is_active: true });

    setTemplateComposer(true);

  };



  // Persist the template from the editor modal.

  const submitTemplate = async () => {

    setTemplateError(null);

    if (!templateForm.name.trim()) { setTemplateError("Give the template a name."); return; }

    try {

      if (editingTemplate && editingTemplate.id) {

        await updateTemplate(editingTemplate.id);

      } else {

        await createTemplate();

      }

      setTemplateComposer(false);

      setEditingTemplate(null);

    } catch (e) {

      setTemplateError(e?.message || String(e));

    }

  };



  // Update template

  const updateTemplate = async (tid) => {

    await api(`/api/templates/${tid}`, {

      method: "POST",

      body: JSON.stringify(templateForm)

    });

    await loadTemplates();

  };



  // Edit template handler

  const handleEditTemplate = (t) => {

    setEditingTemplate(t);

    setTemplateForm({

      name: t.name || "",

      category: t.category || "intro",

      subject_template: t.subject_template || "",

      body_template: t.body_template || "",

      variables: t.variables || {},

      tags: t.tags || [],

      is_active: t.is_active

    });

  };



  // Delete template

  const deleteTemplate = async (tid) => {

    setTemplateDraftError(null);

    try {

      await api(`/api/templates/${tid}`, { method: "DELETE" });

      await loadTemplates();

    } catch (e) {

      setTemplateDraftError(e.message || "Could not delete template");

    }

  };



  // Duplicate template

  const duplicateTemplate = async (tid) => {

    await api(`/api/templates/${tid}/duplicate`, { method: "POST" });

    await loadTemplates();

  };



  // Verification functions

  const loadVerifications = useCallback(async () => {

    try {

      setVerificationLoading(true);

      const [stats, vers] = await Promise.all([

        api("/api/verifications/stats"),

        api("/api/verifications?limit=500")

      ]);

      setVerificationStats(stats);

      setVerifications(Array.isArray(vers) ? vers : []);

    } catch (e) {

      console.error("Failed to load verifications:", e);

    } finally {

      setVerificationLoading(false);

    }

  }, []);



  const loadVerificationsIfNeeded = useCallback(() => {

    if (view === "verifications") {

      loadVerifications();

    }

  }, [view, loadVerifications]);



  useEffect(() => {

    if (!user) return;

    loadVerificationsIfNeeded();

  }, [user, loadVerificationsIfNeeded]);



  // Inbox (IMAP)

  const [inbox, setInbox] = useState({ configured: false, messages: [] });

  const [inboxBusy, setInboxBusy] = useState(false);

  const [inboxError, setInboxError] = useState(null);



  const loadInbox = useCallback(async () => {

    try {

      setInboxError(null);

      const data = await api("/api/inbox?limit=50");

      setInbox({

        configured: Boolean(data?.configured),

        messages: Array.isArray(data?.messages) ? data.messages : [],

      });

    } catch (e) {

      setInboxError(e.message);

    }

  }, []);


  useEffect(() => {

    if (user && view === "inbox") loadInbox();

  }, [user, view, loadInbox]);

  useEffect(() => {

    if (user && view === "campaigns") loadCampaigns();

  }, [user, view, loadCampaigns]);



  const syncInboxNow = async () => {

    setInboxBusy(true);

    setInboxError(null);

    try {

      await api("/api/inbox/sync", { method: "POST" });

      await loadInbox();

    } catch (e) {

      setInboxError(e.message);

    } finally {

      setInboxBusy(false);

    }

  };



  const startBulkVerify = async (contactIds) => {

    if (!contactIds.length) return;

    try {

      const job = await api("/api/verifications/bulk", {

        method: "POST",

        body: JSON.stringify({ contact_ids: contactIds, check_smtp: true, check_catch_all: true })

      });

      setVerifyJob(job);

      setVerifyProgress({processed:0,total:job.total,deliverable:0,undeliverable:0,risky:0,inconclusive:0});

      setVerifyModalOpen(true);

      pollVerifyJob(job.id);

    } catch (e) {

      setError(e?.message || String(e));

    }

  };



  const pollVerifyJob = async (jobId) => {

    try {

      const job = await api(`/api/verifications/bulk/${jobId}`);

      setVerifyJob(job);

      setVerifyProgress({

        processed: job.processed,

        total: job.total,

        deliverable: job.deliverable,

        undeliverable: job.undeliverable,

        risky: job.risky,

        inconclusive: job.inconclusive

      });

      if (job.status === "running" || job.status === "pending") {

        setTimeout(() => pollVerifyJob(jobId), 2000);

      } else if (job.status === "completed") {

        setStatus(`Verification complete: ${job.deliverable} deliverable, ${job.undeliverable} undeliverable, ${job.risky} risky`);

        setTimeout(() => setStatus(null), 4000);

        await loadVerifications();

        await load(); // Refresh contacts for eligibility changes

      } else if (job.status === "failed") {

        setError(job.error || "Verification job failed");

      }

    } catch (e) {

      console.error("Poll verification job failed:", e);

    }

  };



  const handleVerifySelected = () => {

    const ids = Array.from(selectedContacts);

    if (ids.length === 0) return;

    startBulkVerify(ids);

    setSelectedContacts(new Set());

    setSelectAllContacts(false);

  };



  const handleSendSelected = async (templateId) => {

    if (selectedContacts.size === 0) return;

    setSendSelectedTemplate(templateId);

    // Send gating is about saved configuration, not about the last connection
    // test: a test that fails on a flaky network must not lock the workspace
    // out of sending. The server still refuses to send when SMTP is unusable,
    // and the failure is reported by the send itself.
    const smtpIsReady = Boolean(smtpConfig?.configured && !smtpDirty);

    setSendSelectedSmtpReady(smtpIsReady);

    setSendSelectedOpen(true);

  };



  const confirmSendSelected = async () => {

    if (!sendSelectedTemplate) return;

    try {

      const ids = Array.from(selectedContacts);

      const result = await api("/api/queue/run-all", {

        method: "POST",

        body: JSON.stringify({ 

          template_id: sendSelectedTemplate,

          contact_ids: ids

        })

      });

      setStatus(`Sending to ${ids.length} contact(s)...`);

      setTimeout(() => {

        if (result.result?.sent > 0) {

          setStatus(`Sent ${result.result.sent} email(s)`);

        } else if (result.queued) {

          setStatus(`Queued ${ids.length} contact(s); sending continues in the background.`);

        } else {

          setStatus(result.message || "No emails sent");

        }

        setTimeout(() => setStatus(null), 4000);

      }, 1000);

      await load();

      // Paced sends finish server-side; follow the job so the counters settle.
      if (result.job_id) {

        for (let attempt = 0; attempt < 120; attempt += 1) {

          await new Promise(resolve => setTimeout(resolve, 5000));

          try {

            const job = await api(`/api/queue/jobs/${result.job_id}`);

            await load();

            if (job.status === "complete" || job.status === "failed") {

              const jr = job.result || {};

              setStatus(

                job.status === "failed"

                  ? `Background send failed: ${job.error || "unknown error"}`

                  : `Finished: ${jr.sent || 0} sent, ${jr.failed || 0} failed${jr.paused ? " (stopped by a sending limit)" : ""}`

              );

              setTimeout(() => setStatus(null), 6000);

              break;

            }

          } catch { break; }

        }

      }

      setSelectedContacts(new Set());

      setSelectAllContacts(false);

    } catch (e) {

      setError(e?.message || String(e));

    } finally {

      setSendSelectedOpen(false);

      setSendSelectedTemplate(null);

    }

  };



  const toggleSelectAll = () => {

    if (selectAllContacts) {

      setSelectedContacts(new Set());

    } else {

      // Mirror exactly what the table shows: the active segment plus search.
      setSelectedContacts(new Set(filteredContacts.map(c => c.id)));

    }

    setSelectAllContacts(!selectAllContacts);

  };



  const toggleContactSelection = (contactId) => {
    setSelectedContacts(prev => {
      const next = new Set(prev);
      if (next.has(contactId)) next.delete(contactId);
      else next.add(contactId);
      return next;
    });
  };

  // Delete single contact
  const deleteContact = async (contactId) => {
    const target = state.contacts?.find(c => c.id === contactId);
    confirmAction({
      title: "Delete this contact?",
      message: `${target?.email || "This contact"} will be removed together with its drafts and event history. This cannot be undone.`,
      onConfirm: async () => {
        try {
          await api("/api/contacts/" + contactId, { method: "DELETE" });
          setSelectedContacts(prev => {
            const next = new Set(prev);
            next.delete(contactId);
            return next;
          });
          setStatus("Contact deleted");
          setTimeout(() => setStatus(null), 2000);
          await load();
        } catch (e) {
          setError(e?.message || String(e));
        }
      },
    });
  };

  // Delete the contacts that are currently selected in the table
  const deleteSelectedContacts = async () => {
    const ids = Array.from(selectedContacts);
    if (!ids.length) return;
    confirmAction({
      title: `Delete ${ids.length} contact(s)?`,
      message: "Their drafts and event history are removed as well. This cannot be undone.",
      onConfirm: async () => {
        try {
          const result = await api("/api/contacts/bulk", {
            method: "DELETE",
            body: JSON.stringify({ contact_ids: ids }),
          });
          setSelectedContacts(new Set());
          setSelectAllContacts(false);
          setStatus(`${result.total_deleted ?? ids.length} contact(s) deleted`);
          setTimeout(() => setStatus(null), 2500);
          await load();
        } catch (e) {
          setError(e?.message || String(e));
        }
      },
    });
  };

  // Delete every contact in the account
  const deleteAllContacts = async () => {
    const total = state.contacts?.length || 0;
    if (!total) return;
    confirmAction({
      title: `Delete all ${total} contact(s)?`,
      message: "Every contact in this workspace is removed, along with their drafts and event history. Lists and templates are kept. This cannot be undone.",
      confirmLabel: `Delete ${total} contact(s)`,
      onConfirm: async () => {
        try {
          const result = await api("/api/contacts/all?confirm=true", { method: "DELETE" });
          setSelectedContacts(new Set());
          setSelectAllContacts(false);
          setStatus(`${result.total_deleted ?? 0} contact(s) deleted`);
          setTimeout(() => setStatus(null), 2500);
          await load();
        } catch (e) {
          setError(e?.message || String(e));
        }
      },
    });
  };

  const getStatusBadge = (status) => {

    const styles = {

      deliverable: "border-brand-200 bg-brand-50 text-brand-700",

      undeliverable: "border-danger-200 bg-danger-50 text-danger-700",

      risky: "border-warn-200 bg-warn-50 text-warn-700",

      inconclusive: "border-ink-200 bg-ink-100 text-ink-600",

      not_checked: "border-ink-200 bg-ink-100 text-ink-500"

    };

    const icons = {

      deliverable: <CheckCircle className="mr-1 h-3 w-3"/>,

      undeliverable: <XCircle className="mr-1 h-3 w-3"/>,

      risky: <AlertTriangle className="mr-1 h-3 w-3"/>,

      inconclusive: <AlertCircle className="mr-1 h-3 w-3"/>,

      not_checked: <Loader2 className="mr-1 h-3 w-3 animate-spin"/>

    };

    const label = status.charAt(0).toUpperCase() + status.slice(1).replace("_", " ");

    return (

      <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${styles[status] || styles.not_checked}`}>

        {icons[status] || icons.not_checked}

        {label}

      </span>

    );

  };



  const handleReverify = async (verification) => {

    try {

      await api(`/api/verifications/${verification.id}/reverify`, { method: "POST" });

      await loadVerifications();

    } catch (e) {

      setError(e?.message || String(e));

    }

  };



  const handleDeleteVerification = async (id) => {

    confirmAction({
      title: "Delete this verification record?",
      message: "The verification result is removed from the list. You can run the check again at any time.",
      onConfirm: async () => {
        try {

          await api(`/api/verifications/${id}`, { method: "DELETE" });

          await loadVerifications();

        } catch (e) {

          setError(e?.message || String(e));

        }
      },
    });

  };



  // keep the settings form in sync with the server until the user edits it

  useEffect(()=>{

    if(!settingsDirty&&state.settings){

      setSettingsForm({

        goal:state.settings.goal||"",

        business_name:state.settings.business_name||"",

        business_offer:state.settings.business_offer||"",

        tracking_enabled:!!state.settings.tracking_enabled,

      });

    }

  },[state.settings,settingsDirty]);



  useEffect(()=>{

    if(!user) return undefined;

    let active=true;

    (async () => {

      try {

        const config = await api("/api/smtp/status");

        if(!active)return;

        setSmtpConfig(config);

        setSmtp((current)=>({

          ...current,

          host:config.host||"",

          port:String(config.port||587),

          user:config.user||"",

          sender:config.sender||"",

          pass:"",

        }));

        setSmtpDirty(false);

        setSmtpError(null);

        

        // Auto-test SMTP connection if already configured

        if (config?.configured && (config?.authentication_configured || config?.transport === "gmail_api")) {

          try {

            const result = await api("/api/smtp/test", {

              method: "POST",

              body: JSON.stringify({

                host: config.host,

                port: config.port,

                user: config.user,

                password: ""  // Will use saved password from DB

              })

            });

            if (active) {

              setSmtpCheck(result);

              console.log("Auto SMTP test result:", result);

            }

          } catch (e) {

            if (active) setSmtpCheck({ok:false,message:e?.message||String(e)});

          }

        }

      } catch(e) {

        if(active)setSmtpError(e?.message||String(e));

      }

      

      // Inbox mailbox (IMAP)

      try {

        const config = await api("/api/inbox/status");

        if(!active)return;

        setImapConfig(config);

        setImap((current)=>({

          ...current,

          host:config.host||"",

          port:String(config.port||993),

          user:config.user||"",

          folder:config.folder||"INBOX",

          pass:"",

        }));

        setImapDirty(false);

        setImapError(null);

      } catch(e) {

        if(active)setImapError(e?.message||String(e));

      }
      

      // Fetch health status

      try {

        const h = await api("/health");

        if(active) setHealth(h);

      } catch({}) {/* ignore health check errors */}

    })();

    

    return ()=>{active=false;};

  },[user]);



  const updateSmtp=(key,value)=>{

    setSmtp((current)=>({...current,[key]:value}));

    setSmtpDirty(true);

    setSmtpCheck(null);

    setSmtpError(null);

  };



  const importCsv=async(file)=>{

    if(!file)return;

    setCsvBusy(true);

    try{

      const text=await file.text();

      const r=await api("/api/contacts/import",{method:"POST",body:JSON.stringify({csv:text})});

      setStatus(r.message||`Imported ${r.imported} contact(s), updated ${r.updated||0}, skipped ${r.skipped||0}`);setTimeout(()=>setStatus(null),4000);

      await load();

    }catch(e){setError(e?.message||String(e));}

    finally{setCsvBusy(false);}

  };



  const updateEligibility=async(contact,eligible)=>{

    if(eligible){

      confirmAction({

        title:"Confirm email permission",

        message:`${contact.email} has opted in or is otherwise eligible to receive email. Marking them eligible lets the autopilot email this contact.`,

        confirmLabel:"Mark eligible",

        tone:"brand",

        onConfirm:()=>applyEligibility(contact,eligible),

      });

      return;

    }

    await applyEligibility(contact,eligible);

  };



  const applyEligibility=async(contact,eligible)=>{

    setEligibilityBusyId(contact.id);

    try{

      await api(`/api/contacts/${contact.id}/eligibility`,{

        method:"POST",

        body:JSON.stringify({eligible_to_email:eligible}),

      });

      setStatus(eligible?"Contact marked eligible to email":"Email permission removed");

      setTimeout(()=>setStatus(null),2000);

      await load();

    }catch(e){setError(e?.message||String(e));}

    finally{setEligibilityBusyId(null);}

  };



  const addContact=async()=>{

    if(!addContactForm.email.trim()){

      setError("Email is required");

      return;

    }

    try{

      await api("/api/contacts",{

        method:"POST",

        body:JSON.stringify({

          email: addContactForm.email.trim(),

          name: addContactForm.name.trim()||undefined,

          company: addContactForm.company.trim()||undefined,

          role: addContactForm.role.trim()||undefined,

          industry: addContactForm.industry.trim()||undefined,

          notes: addContactForm.notes.trim()||undefined,

          eligible_to_email: addContactForm.eligible_to_email

        }),

      });

      setAddContactOpen(false);

      setAddContactForm({email:"",name:"",company:"",role:"",industry:"",notes:"",eligible_to_email:true});

      setStatus("Contact added successfully");

      setTimeout(()=>setStatus(null),2000);

      await load();

    }catch(e){

      setError(e?.message||String(e));

    }

  };



  const updateSettingsField=(key,value)=>{

    setSettingsForm((f)=>({...f,[key]:value}));

    setSettingsDirty(true);

  };



  const saveSettings=async()=>{

    setSavingSettings(true);

    try{

      await api("/api/settings",{method:"POST",body:JSON.stringify(settingsForm)});

      setSettingsDirty(false);

      setStatus("Settings saved");setTimeout(()=>setStatus(null),2000);

      await load();

    }catch(e){setError(e?.message||String(e));}

    finally{setSavingSettings(false);}

  };



  const composeSubmit=async()=>{

    if(!composeForm.contact_id){setDraftError("Pick a contact to write to.");return;}

    if(!composeForm.subject.trim()||!composeForm.body.trim()){setDraftError("Subject and body are required.");return;}

    try{

      await api("/api/drafts/compose",{method:"POST",body:JSON.stringify({...composeForm,contact_id:Number(composeForm.contact_id)})});

      setComposing(false);

      setComposeForm({contact_id:"",subject:"",body:""});

      setStatus("Draft queued, the autopilot will send it");setTimeout(()=>setStatus(null),2500);

      await load();

    }catch(e){setDraftError(e?.message||String(e));}

  };



  const startEdit=(d)=>{

    setEditingId(d.id);

    setEditForm({subject:d.subject,body:d.body});

    setDraftError(null);

  };



  const saveEdit=async(d)=>{

    try{

      await api(`/api/drafts/${d.id}/update`,{method:"POST",body:JSON.stringify(editForm)});

      setEditingId(null);

      setStatus("Draft updated");setTimeout(()=>setStatus(null),1500);

      await load();

    }catch(e){setDraftError(e?.message||String(e));}

  };



  const redraft=async(d)=>{

    setRedraftingId(d.id);

    setDraftError(null);

    try{

      await api(`/api/drafts/${d.id}/redraft`,{method:"POST"});

      setStatus("AI redrafted this email");setTimeout(()=>setStatus(null),2000);

      await load();

    }catch(e){setDraftError(e?.message||String(e));}

    finally{setRedraftingId(null);}

  };



  const checkSmtp=async()=>{

    const gmailApi=smtpConfig?.transport==="gmail_api";
    const port=smtp.port?Number(smtp.port):587;

    if(!gmailApi&&(!Number.isInteger(port)||port<1||port>65535)){

      setSmtpCheck({ok:false,message:"SMTP port must be an integer between 1 and 65535."});

      return;

    }

    try{

      setSmtpCheck({checking:true,message:gmailApi?"Checking Gmail API access...":"Connecting to SMTP server..."});
      const result=await api("/api/smtp/test",{method:"POST",body:JSON.stringify({

        host:gmailApi?undefined:(smtp.host.trim()||undefined),

        port:gmailApi?undefined:port,

        user:gmailApi?undefined:(smtp.user.trim()||undefined),

        password:smtp.pass||undefined,

      })});

      setSmtpCheck(result);

    }catch(e){setSmtpCheck({ok:false,message:e?.message||String(e)});}

  };



  const saveSmtp=async()=>{

    const port=smtp.port?Number(smtp.port):587;

    if(!smtp.host.trim()){

      setSmtpCheck({ok:false,message:"Enter an SMTP host before saving."});

      return;

    }

    if(!Number.isInteger(port)||port<1||port>65535){

      setSmtpCheck({ok:false,message:"SMTP port must be an integer between 1 and 65535."});

      return;

    }

    try{

      await api("/api/smtp/config",{method:"POST",body:JSON.stringify({

        host:smtp.host,

        port,

        user:smtp.user,

        password:smtp.pass,

        sender:smtp.sender,

      })});

      const config=await api("/api/smtp/status");

      setSmtpConfig(config);

      setSmtp((current)=>({...current,pass:""}));

      setSmtpDirty(false);

      setSmtpCheck(null);

      setSmtpError(null);

      setStatus("saved");setTimeout(()=>setStatus(null),1500);

    }catch(e){setSmtpError(e?.message||String(e));}

  };



  const updateImap=(key,value)=>{

    setImap((current)=>({...current,[key]:value}));

    setImapDirty(true);

    setImapCheck(null);

    setImapError(null);

  };



  const checkImap=async()=>{

    const gmailApi=imapConfig?.transport==="gmail_api";
    const port=imap.port?Number(imap.port):993;

    if(!gmailApi&&(!Number.isInteger(port)||port<1||port>65535)){

      setImapCheck({ok:false,message:"IMAP port must be an integer between 1 and 65535."});

      return;

    }

    try{

      setImapCheck({checking:true,message:gmailApi?"Checking Gmail inbox access...":"Connecting to IMAP server..."});
      const result=await api("/api/inbox/test",{method:"POST",body:JSON.stringify(gmailApi?{}:{

        host:imap.host.trim()||undefined,

        port,

        user:imap.user.trim()||undefined,

        password:imap.pass||undefined,

        folder:imap.folder.trim()||"INBOX",

      })});

      setImapCheck(result);

    }catch(e){setImapCheck({ok:false,message:e?.message||String(e)});}

  };



  const saveImap=async()=>{

    const port=imap.port?Number(imap.port):993;

    if(!imap.host.trim()){

      setImapCheck({ok:false,message:"Enter an IMAP host before saving."});

      return;

    }

    if(!Number.isInteger(port)||port<1||port>65535){

      setImapCheck({ok:false,message:"IMAP port must be an integer between 1 and 65535."});

      return;

    }

    try{

      await api("/api/inbox/config",{method:"POST",body:JSON.stringify({

        host:imap.host,

        port,

        user:imap.user,

        password:imap.pass,

        folder:imap.folder,

      })});

      const config=await api("/api/inbox/status");

      setImapConfig(config);

      setImap((current)=>({...current,pass:""}));

      setImapDirty(false);

      setImapCheck(null);

      setImapError(null);

      setStatus("saved");setTimeout(()=>setStatus(null),1500);

    }catch(e){setImapError(e?.message||String(e));}

  };



  const approveAndSend=async(draft)=>{

    const recipient=state.contacts.find((contact)=>contact.id===draft.contact_id);

    if(!recipient?.email){

      setDraftError("Cannot send this draft because its contact email is missing.");

      return;

    }

    if(!recipient.eligible_to_email){

      setDraftError("This contact is not marked eligible to email. Confirm permission in Contacts before sending.");

      return;

    }

    if(!smtpConfig?.configured||smtpDirty){

      setDraftError("Configure the mail transport in Settings before sending.");

      return;

    }

    confirmAction({
      title: `Send "${draft.subject}" now?`,
      message: `This sends real email to ${recipient.email} over SMTP, outside the review queue.`,
      confirmLabel: "Send now",
      tone: "brand",
      onConfirm: () => sendDraftNow(draft),
    });

  };



  const sendDraftNow=async(draft)=>{

    setSendingDraftId(draft.id);

    setDraftError(null);

    try{

      await api(`/api/drafts/${draft.id}/send`,{method:"POST"});

      const refreshed=normalizeState(await api("/api/state"));

      setState(refreshed);

      const updated=refreshed.drafts.find((item)=>item.id===draft.id);

      if(updated?.status==="sent"){

        setStatus("Email sent successfully");

        setTimeout(()=>setStatus(null),2500);

      }else{

        setDraftError(`Draft was not marked sent (current status: ${updated?.status||"unknown"}). Check mail settings and server logs before retrying.`);

      }

    }catch(e){

      setDraftError(e?.message||String(e));

    }finally{

      setSendingDraftId(null);

    }

  };



  const smtpReady=Boolean(smtpConfig?.configured && !smtpDirty);



  const draftBlockReason=(draft)=>{

    if(draft.status==="sent") return "Already sent";

    if(!smtpConfig?.configured) return "Mail transport not configured";

    if(smtpDirty) return "Save SMTP changes";

    const recipient=state.contacts.find(c=>c.id===draft.contact_id);

    if(!recipient) return "Recipient missing";

    if(!recipient.eligible_to_email) return "Recipient not eligible";

    return "";

  };



  const sortedDrafts=[...state.drafts].sort((a,b)=>(b.id||0)-(a.id||0));



  const items=[

    {group:"Workspace",id:"overview",icon:BarChart3,label:"Overview"},

    {group:"Workspace",id:"agents",icon:Brain,label:"Agents"},

    {group:"Audience",id:"contacts",icon:Users,label:"Contacts",badge:state.contacts?.length||null},

    {group:"Audience",id:"templates",icon:PenLine,label:"Templates"},

    {group:"Campaigns",id:"campaigns",icon:Send,label:"Campaigns"},

    {group:"Campaigns",id:"drafts",icon:FileText,label:"Drafts",badge:state.drafts?.filter(d=>d.status==="draft").length||null},

    {group:"Campaigns",id:"history",icon:Mail,label:"Email history"},

    {group:"Campaigns",id:"experiments",icon:Sparkles,label:"Experiments"},

    {group:"Deliverability",id:"inbox",icon:Inbox,label:"Inbox"},

    {group:"Deliverability",id:"verifications",icon:Shield,label:"Verifications"},

    {group:"Operations",id:"automation",icon:Activity,label:"Automation"},

    ...(user?.role==="admin"?[{group:"Operations",id:"team",icon:Users,label:"Team"}]:[]),

    {group:"Operations",id:"settings",icon:Settings,label:"Settings"},

  ];

  const navGroups=items.reduce((acc,it)=>{

    const last=acc[acc.length-1];

    if(last&&last.name===it.group) last.items.push(it);

    else acc.push({name:it.group,items:[it]});

    return acc;

  },[]);

  const currentItem=items.find(it=>it.id===view);



  const systemLive=health?.status==="healthy";



  useEffect(()=>{
    const timer=setTimeout(()=>setSplashDone(true), 1300);
    return ()=>clearTimeout(timer);
  },[]);

  if(error){

    return (

      <div className="flex h-screen items-center justify-center bg-ink-50 text-ink-900">

        <ErrorDisplay err={error} onRetry={load}/>

      </div>

    );

  }



  if(!user){

    return <Splash/>;

  }



  if(loading){

    return <Splash/>;

  }



  return (

    <>
      {!splashDone && <Splash/>}
      <div className="app-shell shell-in">

      <aside id="app-rail" className={"app-rail " + (navOpen?"app-rail-open":"")}>

        <div className="flex h-16 items-center gap-2.5 border-b border-ink-200 px-4 max-md:px-3">
          <div className="brand-mark">
            <Mail className="h-[18px] w-[18px]"/>
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] font-bold leading-5 tracking-tight">{BRAND_NAME}</div>
            <div className="truncate text-[11px] leading-4 text-ink-500">{user?.tenant?.name||"Workspace"}</div>
          </div>
          <button onClick={()=>setNavOpen(false)} className="icon-btn md:hidden" title="Close menu" aria-label="Close menu"><X className="h-4 w-4"/></button>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2.5 py-3">

          {navGroups.map(group=>(

            <div key={group.name}>

              <div className="rail-label">{group.name}</div>

              <div className="space-y-0.5">

                {group.items.map(it=>(
                  <NavItem key={it.id} icon={it.icon} label={it.label} badge={it.badge} active={view===it.id} onClick={()=>setView(it.id)}/>
                ))}

              </div>

            </div>

          ))}

        </nav>

        <div className="border-t border-ink-200 p-3">

          <div className="flex items-center justify-between rounded-[10px] border border-ink-200 bg-ink-50 px-2.5 py-2">
            <div className="flex items-center gap-2">
              <span className={"h-2 w-2 rounded-full "+(systemLive?"bg-brand-500":"bg-warn-500")}/>
              <span className="text-[12px] font-medium text-ink-700">{systemLive?"All systems live":"Degraded"}</span>
            </div>
            <span className="text-[11px] tabular-nums text-ink-400">{new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}</span>
          </div>

          {status&&<div className="mt-2 px-1 text-[11px] text-info-600">{status}</div>}

          <div className="mt-2.5 flex items-center gap-2 rounded-[10px] px-1 py-1">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-100 text-[11px] font-bold uppercase text-brand-700">
              {(user?.name||user?.email||"?").trim().charAt(0)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12px] font-medium text-ink-800">{user?.name||user?.email}</div>
              <div className="truncate text-[11px] capitalize text-ink-400">{user?.role||"member"}</div>
            </div>
          </div>

        </div>

      </aside>

      {navOpen&&<div className="app-nav-scrim md:hidden" onClick={()=>setNavOpen(false)} aria-hidden="true"/>}

      <main className="app-main">

        <header className="app-topbar">

          <div className="flex min-w-0 items-center gap-2.5">

            <button
              onClick={()=>setNavOpen(true)}
              className="icon-btn -ml-1.5 md:hidden"
              aria-label="Open navigation menu"
              aria-expanded={navOpen}
              aria-controls="app-rail"
            >
              <Menu className="h-5 w-5"/>
            </button>

            <h1 className="truncate text-[15px] font-semibold text-ink-900">{currentItem?.label||"Overview"}</h1>

            <span className="chip max-sm:hidden">{user?.tenant?.name||"Workspace"}</span>

          </div>

          <div className="flex shrink-0 items-center gap-2">

            <button onClick={run} className="btn-primary btn-sm"><Play className="h-3.5 w-3.5"/><span className="max-sm:hidden">Run now</span><span className="sm:hidden">Run</span></button>

            <button onClick={load} aria-label="Refresh dashboard" className="btn-ghost btn-sm"><RefreshCw className="h-3.5 w-3.5"/><span className="max-sm:hidden">Refresh</span></button>

          </div>

        </header>

        <div className={"flex-1 min-h-0 " + (view==="contacts"||view==="campaigns" ? "overflow-hidden" : "app-body")}>

          <div className={view==="contacts"||view==="campaigns" ? "h-full" : "page"}>

          {view==="overview"&&(

            <>

              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">

                <StatCard label="Contacts" value={state.contacts?.length||0} icon={Users} hint="In this workspace"/>

                <StatCard label="Sent" value={analytics.sent||0} icon={Send} color="green" hint="All time"/>

                <StatCard label="Replies" value={analytics.replied||0} icon={Mail} color="blue" hint="All time"/>

                <StatCard label="Reply rate" value={(analytics.reply_rate||0)+"%"} icon={TrendingUp} color="yellow" hint="Replies ÷ sent"/>

              </div>

              <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">

                <MetricSection
                  tone="green"
                  icon={Send}
                  title="Emails sent"
                  headline={analytics.sent||0}
                  headlineHint="all time"
                  rows={[
                    ["Today", usage?.today?.emails_sent??0],
                    ["Pending drafts", analytics.pending||0],
                    ["Failed sends", analytics.failed||0],
                  ]}
                  footer={usage?.daily_email_limit?`Daily allowance ${usage.today?.emails_sent||0} / ${usage.daily_email_limit}`:null}
                />

                <MetricSection
                  tone="blue"
                  icon={Inbox}
                  title="Replies received"
                  headline={analytics.replied||0}
                  headlineHint="all time"
                  rows={[
                    ["Reply rate", (analytics.reply_rate||0)+"%"],
                    ["Auto-replies sent", analytics.auto_replies||0],
                    ["Awaiting reply", Math.max(0,(analytics.sent||0)-(analytics.replied||0))],
                  ]}
                  footer={analytics.replied?"Answering automatically":"No replies yet"}
                />

                <MetricSection
                  tone="yellow"
                  icon={RefreshCw}
                  title="Follow-ups sent"
                  headline={analytics.followups_sent||0}
                  headlineHint="all time"
                  rows={[
                    ["Waiting in queue", analytics.followups_due||0],
                    ["Total follow-ups", (analytics.followups_sent||0)+(analytics.followups_due||0)],
                    ["Cadence", "Day 3 & day 5"],
                  ]}
                  footer="Sent by the same queue, pacing and caps apply"
                />

                <MetricSection
                  tone="green"
                  icon={TrendingUp}
                  title="Interested clients"
                  headline={analytics.interested||0}
                  headlineHint="want to talk"
                  rows={[
                    ["Positive replies", analytics.reply_types?.positive_response||0],
                    ["Call requests", analytics.reply_types?.schedule_call||0],
                    ["Questions", analytics.reply_types?.question||0],
                  ]}
                  footer={(analytics.interested||0)>0?"Follow up personally to close":"No interested clients yet"}
                />

              </div>

              <div className="mt-5 grid gap-4 lg:grid-cols-3">

                <div className="lg:col-span-2">

                  <Card title="Sending — last 14 days" subtitle="Sent versus replied per day">

                    <AnalyticsChart series={analytics.series||[]}/>

                  </Card>

                </div>

                <Card title="Queue health" subtitle="Live pipeline counts">

                  <div className="space-y-2.5">

                    {[["Pending drafts",analytics.pending||0],["Follow-ups due",analytics.followups_due||0],["Auto-replies sent",analytics.auto_replies||0],["Failed sends",analytics.failed||0]].map(([label,value])=>(

                      <div key={label} className="flex items-center justify-between text-[13px]">

                        <span className="text-ink-500">{label}</span>

                        <span className="font-semibold tabular-nums text-ink-900">{value}</span>

                      </div>

                    ))}

                  </div>

                  <div className="mt-4 space-y-2 border-t border-ink-200 pt-3">

                    <div className="flex items-center justify-between text-[13px]">

                      <span className="text-ink-500">Sent today</span>

                      <span className="font-semibold tabular-nums text-ink-900">

                        {usage?.today?.emails_sent??0}

                        {usage?.daily_email_limit?<span className="font-normal text-ink-400"> / {usage.daily_email_limit}</span>:null}

                      </span>

                    </div>

                    {usage?.daily_email_limit?

                      <div className="h-1.5 overflow-hidden rounded-full bg-ink-100">

                        <div className={"h-full rounded-full "+(usage.daily_remaining===0?"bg-danger-500":"bg-brand-500")} style={{width:`${Math.min(100,Math.round(((usage.today?.emails_sent||0)/usage.daily_email_limit)*100))}%`}}/>

                      </div>

                    :null}

                    <div className="flex items-center justify-between text-[12px] text-ink-500">

                      <span>Drafts this month</span>

                      <span className="tabular-nums">{usage?.month?.emails_drafted??0}</span>

                    </div>

                  </div>

                </Card>

              </div>

              <div className="mt-5 grid gap-4">

                <Card title="Recent activity" subtitle="Latest workflow events">

                  <div className="max-h-64 space-y-2.5 overflow-y-auto">

                    {state.logs?.slice(0,10).map(log=>(

                      <div key={log.id} className="flex items-start gap-3 border-b border-ink-100 pb-2 text-[12px] last:border-0 last:pb-0">

                        <span className="shrink-0 tabular-nums text-ink-400">{new Date(log.timestamp).toLocaleString()}</span>

                        <span className="text-ink-700">{log.message}</span>

                      </div>

                    ))}

                    {(!state.logs||state.logs.length===0)&&

                      <p className="text-[12px] text-ink-500">No recent activity.</p>

                    }

                  </div>

                </Card>

              </div>

            </>

          )}

          {view==="templates"&&(

            <div className="space-y-4">

              <PageHeader title="Templates" subtitle="Reusable subjects and bodies with merge variables." eyebrow="Workspace">

                <button onClick={()=>openTemplateComposer(null)} className="btn-primary"><PenLine className="h-3.5 w-3.5"/>New template</button>

              </PageHeader>

              {templateDraftError&&<div className="notice-error">{templateDraftError}</div>}

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">

                {templates.map(template=>(

                  <article
                    key={template.id}
                    onClick={()=>openTemplateComposer(template)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e)=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();openTemplateComposer(template);}}}
                    className="surface flex cursor-pointer flex-col transition-shadow hover:shadow-pop focus:outline-none focus:ring-2 focus:ring-brand-500"
                  >

                    <div className="flex items-start justify-between gap-3 border-b border-ink-100 px-4 py-3">

                      <div className="min-w-0">

                        <h3 className="truncate text-[14px] font-semibold text-ink-900">{template.name}</h3>

                        <div className="mt-1 flex flex-wrap items-center gap-1.5">

                          {template.tags?.map(tag=><Pill key={tag} v={tag}/>)}

                          <Pill v={template.category}/>

                          <span className={"badge "+(template.is_active?"border-brand-200 bg-brand-50 text-brand-700":"border-ink-200 bg-ink-100 text-ink-500")}>{template.is_active?"active":"inactive"}</span>

                        </div>

                      </div>

                      <div className="flex shrink-0 items-center gap-0.5">

                        <button onClick={(e)=>{e.stopPropagation();openTemplateComposer(template);}} className="icon-btn" title="Edit template"><Pencil className="h-4 w-4"/></button>

                        <button onClick={(e)=>{e.stopPropagation();duplicateTemplate(template.id);}} className="icon-btn" title="Duplicate template"><Copy className="h-4 w-4"/></button>

                        <button onClick={(e)=>{e.stopPropagation();deleteTemplate(template.id);}} className="icon-btn hover:bg-danger-50 hover:text-danger-600" title="Delete template"><Trash2 className="h-4 w-4"/></button>

                      </div>

                    </div>

                    <div className="flex flex-1 flex-col px-4 py-3">

                      <p className="line-clamp-2 text-[13px] text-ink-700">{template.subject_template}</p>

                      <p className="mt-auto pt-3 text-[11px] text-ink-400">Variables: {Object.keys(template.variables||{}).join(", ")||"none"}</p>

                    </div>

                  </article>

                ))}

                {templates.length===0&&(

                  <div className="surface col-span-full"><EmptyState icon={PenLine} title="No templates yet" description="Templates are the starting point for every campaign and draft."/></div>

                )}

              </div>

            </div>

          )}

          {view==="agents"&&(

          <div className="space-y-4">

            <PageHeader title="Agents" subtitle="The pipeline runs itself: contacts go in, replies come back answered." eyebrow="Workspace"/>

            <LiveAgentActivity enabled={state.live_logs!==false}/>

            <Card title="Pipeline" subtitle="Runs on the schedule and whenever you press Run now">

              <ol className="space-y-3">

                {[

                  {icon:Users,title:"1. Audience",desc:"Every contact that is eligible for email and has no outreach yet is picked up for an intro.",value:`${analytics.pending||0} drafts waiting`},

                  {icon:PenLine,title:"2. Drafting",desc:"The active intro template is rendered per contact, one draft per new contact.",value:`${state.templates?.length||0} templates`},

                  {icon:Send,title:"3. Sending",desc:"The queue sends those drafts inside the daily limits and pacing, no approval step in between.",value:`${analytics.sent||0} sent`},

                  {icon:Inbox,title:"4. Replies",desc:"New mail is pulled over IMAP, matched to the contact, classified and answered automatically.",value:`${analytics.auto_replies||0} auto-replies`},

                  {icon:RefreshCw,title:"5. Follow-ups",desc:"Day-3 and day-5 follow-ups are drafted for threads without a reply and sent by the same queue.",value:`${analytics.followups_due||0} due`},

                ].map(step=>(

                  <li key={step.title} className="flex items-start gap-3">

                    <span className="stat-icon shrink-0 bg-brand-50 text-brand-600"><step.icon className="h-4 w-4"/></span>

                    <div className="min-w-0 flex-1">

                      <div className="flex items-baseline justify-between gap-3">

                        <p className="text-[13px] font-semibold text-ink-900">{step.title}</p>

                        <span className="shrink-0 text-[11px] tabular-nums text-ink-400">{step.value}</span>

                      </div>

                      <p className="mt-0.5 text-[12.5px] text-ink-500">{step.desc}</p>

                    </div>

                  </li>

                ))}

              </ol>

            </Card>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">

              <Card title="Reply classification">

                <p className="text-[13px] text-ink-500">Each reply is classified as positive, question, negative, unsubscribe or spam. Positive replies and questions get an answer; unsubscribe and spam are recorded and left alone.</p>

              </Card>

              <Card title="Calendar booking">

                <p className="text-[13px] text-ink-500">Not connected. No calendar integration is installed, so this is not automated.</p>

              </Card>

              <Card title="Memory">

                <p className="text-[13px] text-ink-500">Not implemented. Interaction history is stored as events, but the agent does not use it yet.</p>

              </Card>

            </div>

          </div>

        )}

        {view==="contacts"&&(
          <div className="flex h-full min-h-0 flex-col bg-ink-100">
            <div className="page-head page-head-flush">
              <div>
                <div className="breadcrumb mb-1">Audience</div>
                <h1 className="page-title">Contacts</h1>
                <p className="page-subtitle">Manage your contact lists and segments</p>
              </div>
              <div className="flex items-center gap-2">
                <input type="file" accept=".csv" ref={fileInputRef} onChange={e=>{importCsv(e.target.files[0]);e.target.value="";}} className="hidden"/>
                {(state.contacts?.length || 0) > 0 && (
                  <button
                    onClick={deleteAllContacts}
                    className="btn-ghost text-danger-600 hover:bg-danger-50 hover:text-danger-700"
                    title="Delete every contact in this workspace"
                  >
                    <Trash2 className="h-3.5 w-3.5"/>Delete all
                  </button>
                )}
                <button
                  onClick={()=>fileInputRef.current?.click()}
                  className="btn-ghost"
                >
                  <Upload className="h-3.5 w-3.5"/>Import CSV
                </button>
                <button
                  onClick={()=>{setAddContactOpen(true);setAddContactForm({email:"",name:"",company:"",role:"",industry:"",notes:"",eligible_to_email:true});}}
                  className="btn-primary"
                >
                  <Plus className="h-3.5 w-3.5"/>Add contact
                </button>
              </div>
            </div>

            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-200 bg-ink-50 px-5 py-2.5 max-md:px-4">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="flex items-center gap-1.5">
                    <Folder className="h-4 w-4 text-ink-400"/>
                    <select
                      className="select w-auto py-1.5 text-[12.5px]"
                      value={folderFilter}
                      onChange={e => setFolderFilter(e.target.value)}
                    >
                      <option value="all">All folders</option>
                      {folders.map(folder => (
                        <option key={folder.id} value={String(folder.id)}>{folder.name} ({folder.listCount})</option>
                      ))}
                      <option value="none">No folder</option>
                    </select>
                  </div>
                  <button
                    onClick={() => { setShowFolderModal(true); setFolderError(null); }}
                    className="btn-ghost btn-sm"
                  >
                    <FolderPlus className="h-3.5 w-3.5"/>New folder
                  </button>
                  <div className="relative">
                    <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-400"/>
                    <input
                      type="text"
                      placeholder="Search lists..."
                      className="input w-48 py-1.5 pl-8 text-[12.5px]"
                      value={listSearch}
                      onChange={e => setListSearch(e.target.value)}
                    />
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5 text-[12.5px] text-ink-500">
                    <Info className="h-3.5 w-3.5 opacity-70"/>
                    <span className="tabular-nums">{filteredContactsCount} contacts</span>
                  </div>
                  <button
                    onClick={() => { setNewListName(""); setNewListFolder(""); setListError(null); setShowListModal(true); }}
                    className="btn-primary"
                  >
                    <Plus className="h-3.5 w-3.5"/>Create a list
                  </button>
                </div>
              </div>

              {/* List tabs: newest list first, like Brevo */}
              <div className="flex flex-wrap items-center gap-1 border-b border-ink-200 px-5 py-2.5">
                <button
                  onClick={() => setSelectedList("all")}
                  className={selectedList === "all" ? "seg-item-active" : "seg-item"}
                >
                  All contacts <span className="opacity-60">({state.contacts?.length || 0})</span>
                </button>
                <button
                  onClick={() => setSelectedList("eligible")}
                  className={selectedList === "eligible" ? "seg-item-active" : "seg-item"}
                >
                  Eligible
                </button>
                {visibleLists.map(list => (
                  <span key={list.id} className="relative flex items-center">
                    <button
                      onClick={() => setSelectedList(String(list.id))}
                      className={selectedList === String(list.id) ? "seg-item-active rounded-r-none pr-1" : "seg-item rounded-r-none pr-1"}
                      title={list.description || undefined}
                    >
                      {list.name} <span className="opacity-60">({list.total_subscribers ?? list.member_count})</span>
                    </button>
                    <button
                      onClick={() => setOpenListMenu(openListMenu === list.id ? null : list.id)}
                      className={"rounded-r-md py-1.5 pl-1 pr-2 text-[12px] transition-colors " + (selectedList === String(list.id) ? "bg-brand-600 text-white/80 hover:bg-brand-700" : "text-ink-400 hover:bg-ink-100 hover:text-ink-700")}
                      title={`Actions for ${list.name}`}
                      aria-label={`Actions for ${list.name}`}
                    >
                      <MoreHorizontal className="h-4 w-4"/>
                    </button>
                    {openListMenu === list.id && (
                      <div className="absolute left-0 top-full z-30 mt-1 w-56 rounded-xl border border-ink-200 bg-ink-100 py-1 shadow-pop">
                        {[
                          { label: "List settings", icon: SlidersHorizontal, onClick: () => { setShowListSettings(list); setListSettingsForm({ description: list.description || "", from_name: list.from_name || "", from_email: list.from_email || "", reply_to: list.reply_to || "", header: list.header || "", footer: list.footer || "" }); setListError(null); } },
                          { label: "Duplicate", icon: Copy, onClick: () => duplicateList(list.id) },
                          { label: "Import contacts to the list", icon: Upload, onClick: () => { setShowListImport(list); setListImportText(""); setListError(null); } },
                          { label: "Rename", icon: Pencil, onClick: () => { setShowRenameList(list); setRenameListName(list.name); setListError(null); } },
                          { label: "Move", icon: MoveRight, onClick: () => { setShowMoveList(list); setListError(null); } },
                          { label: "Delete list", icon: Trash2, danger: true, onClick: () => { setOpenListMenu(null); deleteList(list.id); } },
                        ].map(item => (
                          <button
                            key={item.label}
                            onClick={() => { setOpenListMenu(null); item.onClick(); }}
                            className={"flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-ink-50 " + (item.danger ? "text-danger-600" : "text-ink-700")}
                          >
                            <item.icon className="h-4 w-4 opacity-70"/>{item.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </span>
                ))}
                {listError && <span className="text-[12px] text-danger-600">{listError}</span>}
              </div>

              {/* List context bar: counts and bulk actions for the open list */}
              {selectedList !== "all" && selectedList !== "eligible" && (
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-200 bg-ink-100 px-5 py-2 text-[12px] text-ink-600">
                  <div className="flex flex-wrap items-center gap-4">
                    <span><strong className="tabular-nums text-ink-900">{filteredContactsCount}</strong> subscribed</span>
                    <span><strong className="tabular-nums text-ink-900">{lists.find(l => String(l.id) === selectedList)?.total_blacklisted ?? 0}</strong> blocklisted</span>
                    <span><strong className="tabular-nums text-ink-900">{lists.find(l => String(l.id) === selectedList)?.unsubscribed_count ?? 0}</strong> unsubscribed</span>
                    <span className="text-ink-400">Newest contacts first</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      onClick={() => { setShowAddToList(lists.find(l => String(l.id) === selectedList)); setAddToListIds([]); setListError(null); }}
                      className="btn-ghost btn-sm"
                    >
                      <Plus className="h-3.5 w-3.5"/>Add contacts
                    </button>
                    <button
                      disabled={listBusy}
                      onClick={() => cleanupListMembers(selectedList, "remove-duplicates")}
                      className="btn-ghost btn-sm"
                      title="Remove contacts from this list when they are also in other lists"
                    >
                      Remove duplicates
                    </button>
                    <button
                      disabled={listBusy}
                      onClick={() => cleanupListMembers(selectedList, "remove-from-other-lists")}
                      className="btn-ghost btn-sm"
                      title="Remove this list's contacts from all other lists"
                    >
                      Remove from other lists
                    </button>
                  </div>
                </div>
              )}

              {listNotice && (
                <div className="border-b border-brand-200 bg-brand-50 px-5 py-2 text-[12px] text-brand-700">{listNotice}</div>
              )}

              {/* Search bar */}
              <div className="flex flex-wrap items-center gap-3 border-b border-ink-200 px-5 py-2.5">
                <div className="relative max-w-md flex-1">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400"/>
                  <input
                    type="text"
                    placeholder="Search contacts..."
                    className="input py-1.5 pl-9 text-[12.5px]"
                    value={contactsSearch}
                    onChange={e => setContactsSearch(e.target.value)}
                  />
                </div>
                {selectedContacts.size > 0 && (
                  <div className="flex flex-wrap items-center gap-2 rounded-lg border border-brand-200 bg-brand-50/60 px-2.5 py-1.5">
                    <span className="text-[12.5px] font-semibold text-brand-800">{selectedContacts.size} selected</span>
                    <select
                      className="select w-auto py-1.5 text-[12.5px]"
                      value=""
                      onChange={async e => {
                        const listId = e.target.value;
                        if (!listId) return;
                        await addContactsToList(listId, Array.from(selectedContacts));
                        setSelectedContacts(new Set());
                        e.target.value = "";
                      }}
                    >
                      <option value="">Add to a list...</option>
                      {lists.map(list => (
                        <option key={list.id} value={list.id}>{list.name}</option>
                      ))}
                    </select>
                    {selectedList !== "all" && selectedList !== "eligible" && (
                      <button
                        onClick={async () => {
                          for (const contactId of Array.from(selectedContacts)) {
                            await removeContactFromList(selectedList, contactId);
                          }
                          setSelectedContacts(new Set());
                        }}
                        className="btn-ghost btn-sm"
                      >
                        Remove from this list
                      </button>
                    )}
                    <button
                      onClick={deleteSelectedContacts}
                      className="btn-sm inline-flex items-center gap-1.5 rounded-lg border border-danger-200 bg-ink-100 font-medium text-danger-600 hover:bg-danger-50 hover:text-danger-700"
                      title="Delete the selected contacts"
                    >
                      <Trash2 className="h-3.5 w-3.5"/>Delete
                    </button>
                    <button
                      onClick={() => { setSelectedContacts(new Set()); setSelectAllContacts(false); }}
                      className="icon-btn"
                      title="Clear selection"
                      aria-label="Clear selection"
                    >
                      <X className="h-4 w-4"/>
                    </button>
                  </div>
                )}
              </div>

              {/* Contacts table */}
              <div className="min-h-0 flex-1 overflow-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>
                        <button
                          onClick={toggleSelectAll}
                          className="flex items-center gap-2.5 hover:text-ink-900"
                          title={selectAllContacts?"Clear selection":"Select all visible contacts"}
                        >
                          <span
                            className={
                              "flex h-4 w-4 shrink-0 items-center justify-center rounded-[5px] border transition-colors " +
                              (selectedContacts.size > 0
                                ? "border-brand-600 bg-brand-600 text-white"
                                : "border-ink-300 bg-ink-100")
                            }
                          >
                            {selectedContacts.size > 0 && selectedContacts.size >= filteredContacts.length
                              ? <Check className="h-3 w-3"/>
                              : selectedContacts.size > 0
                                ? <span className="h-0.5 w-2 rounded-full bg-ink-100"/>
                                : null}
                          </span>
                          Contact
                        </button>
                      </th>
                      <th className="text-center">Subscribed</th>
                      <th className="text-center">Blocklisted</th>
                      <th>Email</th>
                      <th className="text-center">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredContacts.map(contact=>{
                      const isSelected = selectedContacts.has(contact.id);
                      return (
                      <tr key={contact.id} className={isSelected ? "bg-brand-50/50" : undefined}>
                        <td>
                          <div className="flex items-center gap-2.5">
                            <button
                              onClick={() => toggleContactSelection(contact.id)}
                              className={
                                "flex h-4 w-4 shrink-0 items-center justify-center rounded-[5px] border transition-colors " +
                                (isSelected
                                  ? "border-brand-600 bg-brand-600 text-white"
                                  : "border-ink-300 bg-ink-100 hover:border-brand-400")
                              }
                              title={isSelected ? "Deselect contact" : "Select contact"}
                              aria-label={isSelected ? `Deselect ${contact.email}` : `Select ${contact.email}`}
                            >
                              {isSelected ? <Check className="h-3 w-3"/> : null}
                            </button>
                            <div className="min-w-0">
                              <div className="truncate font-medium text-ink-900">{contact.name||"-"}</div>
                              {contact.company && <div className="truncate text-[11.5px] text-ink-500">{contact.company}</div>}
                            </div>
                          </div>
                        </td>
                        <td className="text-center">
                          <button
                            onClick={()=>updateEligibility(contact,!contact.eligible_to_email)}
                            disabled={eligibilityBusyId===contact.id}
                            className={"badge cursor-pointer " + (contact.eligible_to_email ? "border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100" : "border-ink-200 bg-ink-100 text-ink-500 hover:bg-ink-200") + (eligibilityBusyId===contact.id?" opacity-50":"")}
                            title={contact.eligible_to_email?"Click to remove email permission":"Click to confirm opt-in eligibility"}
                          >
                            {contact.eligible_to_email ? "Yes" : "No"}
                          </button>
                        </td>
                        <td className="text-center">
                          <span className={"badge " + (contact.email_blacklisted ? "border-danger-200 bg-danger-50 text-danger-700" : "border-ink-200 bg-ink-100 text-ink-500")}>
                            {contact.email_blacklisted ? "Yes" : "No"}
                          </span>
                        </td>
                        <td>
                          <a href={"mailto:" + contact.email} className="link">
                            {contact.email}
                          </a>
                        </td>
                        <td className="text-center">
                          <div className="flex items-center justify-center gap-0.5">
                            <button
                              onClick={()=>{setComposeForm({contact_id:String(contact.id),subject:"",body:""});setDraftError(null);setComposing(true);}}
                              className="icon-btn"
                              title="Write email"
                              aria-label={`Write email to ${contact.email}`}
                            >
                              <PenLine className="h-4 w-4"/>
                            </button>
                            <button
                              onClick={()=>deleteContact(contact.id)}
                              className="icon-btn hover:bg-danger-50 hover:text-danger-600"
                              title="Delete contact"
                              aria-label={`Delete ${contact.email}`}
                            >
                              <Trash2 className="h-4 w-4"/>
                            </button>
                          </div>
                        </td>
                      </tr>
                      );
                    })}
                    {(filteredContactsCount===0 || !filteredContacts.length)&&(
                      <tr>
                        <td colSpan={5} className="table-empty">
                          <div className="flex flex-col items-center gap-3 py-4">
                            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-ink-100 text-ink-400"><Users className="h-5 w-5"/></span>
                            <div>
                              <p className="text-[13.5px] font-semibold text-ink-900">
                                {contactsSearch.trim() ? "No contacts match your search" : "No contacts yet"}
                              </p>
                              <p className="mt-1 text-[12.5px] text-ink-500">
                                {contactsSearch.trim()
                                  ? "Try a different name, company or email address."
                                  : "Add a contact by hand or import a CSV to get started."}
                              </p>
                            </div>
                            {!contactsSearch.trim() && (
                              <div className="flex items-center gap-2">
                                <button
                                  onClick={()=>fileInputRef.current?.click()}
                                  className="btn-ghost btn-sm"
                                >
                                  <Upload className="h-3.5 w-3.5"/>Import CSV
                                </button>
                                <button
                                  onClick={()=>{setAddContactOpen(true);setAddContactForm({email:"",name:"",company:"",role:"",industry:"",notes:"",eligible_to_email:true});}}
                                  className="btn-primary btn-sm"
                                >
                                  <Plus className="h-3.5 w-3.5"/>Add contact
                                </button>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        ) }{view==="campaigns"&&(

          <div className="flex h-full min-h-0 flex-col bg-ink-100">

            <div className="page-head page-head-flush">

              <div>

                <div className="breadcrumb mb-1">Campaigns</div>

                <h1 className="page-title">Campaigns</h1>

                <p className="page-subtitle">Design and send campaigns to your contact lists</p>

              </div>

              <div className="flex items-center gap-2">

                <button
                  onClick={loadCampaigns}
                  className="btn-ghost"
                >
                  <RefreshCw className={"h-3.5 w-3.5 " + (campaignsLoading ? "animate-spin" : "")}/>Refresh
                </button>

                <button
                  onClick={openCampaignEditor}
                  className="btn-primary"
                >
                  <Plus className="h-3.5 w-3.5"/>Create a campaign
                </button>

              </div>

            </div>

            {campaignNotice && (
              <div className="mx-5 mt-3 notice-ok">{campaignNotice}</div>
            )}
            {campaignError && (
              <div className="mx-5 mt-3 notice-error">{campaignError}</div>
            )}

            {/* Channel picker: email only. SMS, push and WhatsApp need providers
                this app does not ship, so they are not offered. */}
            <div className="border-b border-ink-200 bg-ink-50 px-5 py-3 max-md:px-4">
              <p className="mb-2.5 text-[12.5px] font-medium text-ink-600">Channel</p>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => setCampaignChannel("email")}
                  title="Email campaign"
                  className={
                    "flex items-center gap-2 rounded-[9px] border px-3 py-1.5 text-[12.5px] font-medium transition-colors " +
                    (campaignChannel === "email"
                      ? "border-brand-600 bg-brand-50 text-brand-700"
                      : "border-ink-200 bg-ink-100 text-ink-600 hover:bg-ink-200/60")
                  }
                >
                  <Mail className="h-3.5 w-3.5"/>Email
                </button>
              </div>
            </div>

            {/* Filters */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-200 px-5 py-2.5 max-md:px-4">
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-400"/>
                  <input
                    type="text"
                    placeholder="Search campaigns..."
                    value={campaignSearch}
                    onChange={e => setCampaignSearch(e.target.value)}
                    className="input w-56 py-1.5 pl-8 text-[12.5px]"
                  />
                </div>
                <select
                  value={campaignStatusFilter}
                  onChange={e => setCampaignStatusFilter(e.target.value)}
                  className="select w-auto py-1.5 text-[12.5px]"
                >
                  <option value="all">All statuses</option>
                  <option value="draft">Draft</option>
                  <option value="scheduled">Scheduled</option>
                  <option value="sent">Sent</option>
                  <option value="paused">Paused</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </div>
              <p className="text-[12.5px] tabular-nums text-ink-500">{visibleCampaigns.length} campaign(s)</p>
            </div>

            <div className="min-h-0 flex-1 overflow-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Campaign</th>
                    <th>Status</th>
                    <th>List</th>
                    <th className="text-right">Recipients</th>
                    <th className="text-right">Delivered</th>
                    <th className="text-right">Opened</th>
                    <th className="text-right">Clicked</th>
                    <th>Sent</th>
                    <th/>
                  </tr>
                </thead>
                <tbody>
                  {visibleCampaigns.map(campaign => (
                    <tr key={campaign.id}>
                      <td>
                        <button onClick={() => openCampaignDetail(campaign)} className="text-left">
                          <div className="font-medium text-ink-900">{campaign.name}</div>
                          <div className="text-[11.5px] text-ink-500">{campaign.subject || "No subject yet"}</div>
                        </button>
                      </td>
                      <td><StatusPill status={campaign.status}/></td>
                      <td className="text-ink-700">{campaign.list_name || "All contacts"}</td>
                      <td className="text-right tabular-nums text-ink-700">{campaign.total_recipients}</td>
                      <td className="text-right tabular-nums text-ink-700">{campaign.delivered}</td>
                      <td className="text-right tabular-nums text-ink-700">{campaign.opened}<span className="ml-1 text-[11px] text-ink-400">{campaign.open_rate}%</span></td>
                      <td className="text-right tabular-nums text-ink-700">{campaign.clicked}<span className="ml-1 text-[11px] text-ink-400">{campaign.click_rate}%</span></td>
                      <td className="whitespace-nowrap text-[11.5px] text-ink-500">{campaign.sent_at ? new Date(campaign.sent_at).toLocaleDateString() : "—"}</td>
                      <td className="text-right">
                        <div className="relative flex items-center justify-end gap-1">
                          {["draft", "scheduled", "paused"].includes(campaign.status) && (
                            <button
                              onClick={() => sendCampaign(campaign)}
                              disabled={campaignBusy}
                              className="btn-ghost btn-sm"
                            >
                              Send
                            </button>
                          )}
                          <button
                            onClick={() => setOpenCampaignMenu(openCampaignMenu === campaign.id ? null : campaign.id)}
                            className="icon-btn"
                            aria-label={`Actions for ${campaign.name}`}
                          >
                            <MoreHorizontal className="h-4 w-4"/>
                          </button>
                          {openCampaignMenu === campaign.id && (
                            <div className="absolute right-0 top-full z-30 mt-1 w-52 rounded-xl border border-ink-200 bg-ink-100 py-1 shadow-pop">
                              {[
                                { label: "Campaign stats", icon: BarChart3, onClick: () => openCampaignDetail(campaign) },
                                { label: "Duplicate", icon: Copy, onClick: () => duplicateCampaign(campaign.id) },
                                { label: "Pause", icon: Activity, onClick: () => setCampaignState(campaign.id, "pause"), hide: !["draft", "scheduled"].includes(campaign.status) },
                                { label: "Cancel", icon: XCircle, onClick: () => setCampaignState(campaign.id, "cancel"), hide: ["sent", "cancelled"].includes(campaign.status) },
                                { label: "Delete campaign", icon: Trash2, danger: true, onClick: () => deleteCampaign(campaign.id) },
                              ].filter(item => !item.hide).map(item => (
                                <button
                                  key={item.label}
                                  onClick={() => { setOpenCampaignMenu(null); item.onClick(); }}
                                  className={"flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-ink-50 " + (item.danger ? "text-danger-600" : "text-ink-700")}
                                >
                                  <item.icon className="h-3.5 w-3.5 opacity-70"/>{item.label}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                  {visibleCampaigns.length === 0 && (
                    <tr>
                      <td colSpan={9}>
                        <EmptyState
                          icon={Send}
                          title="Your clients have never been closer"
                          description="No matter how you want to reach out, create your first campaign to get started."
                          action={<button onClick={openCampaignEditor} className="btn-primary mt-3">Create a campaign</button>}
                        />
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        ) }{view==="drafts"&&(

          <div className="space-y-4">

            <PageHeader title="Drafts" subtitle="Review each message before it leaves your mailbox." eyebrow="Campaigns">

              <button

                onClick={()=>{setComposeForm({contact_id:"",subject:"",body:""});setDraftError(null);setComposing(true);}}

                className="btn-ghost"

              >

                <PenLine className="h-3.5 w-3.5"/>Write email

              </button>

            </PageHeader>

            {!smtpReady&&(

              <div className="notice-warn flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">

                <span>{smtpConfig?.configured ? "Test the mail connection in Settings to enable sending." : "Configure the mail transport in Settings to enable sending."}</span>

                <button type="button" onClick={()=>setView("settings")} className="shrink-0 font-semibold underline underline-offset-2">Open mail settings</button>

              </div>

            )}

            {draftError&&<div className="notice-error">{draftError}</div>}

            <Card title={`${sortedDrafts.length} draft${sortedDrafts.length===1?"":"s"}`} subtitle="Click a row to edit; send when the recipient is eligible.">

              <div className="-mx-5 -my-4 overflow-x-auto">

                <table className="data-table">

                  <thead>

                    <tr>

                      <th className="w-[34%]">To</th>

                      <th className="w-[38%]">Subject</th>

                      <th className="w-[14%]">Status</th>

                      <th className="w-[14%] text-right">Action</th>

                    </tr>

                  </thead>

                  <tbody>

                    {sortedDrafts.map(draft=>{

                      const recipient=state.contacts.find(c=>c.id===draft.contact_id);

                      const canSend=draft.status!=="sent"&&smtpReady&&Boolean(recipient?.eligible_to_email);

                      return (

                        <tr key={draft.id} onClick={()=>startEdit(draft)} className="cursor-pointer">

                          <td>

                            <div className="font-medium text-ink-900">{recipient?.name||recipient?.email||"Unknown contact"}</div>

                            {recipient?.email&&<div className="mt-0.5 text-[11.5px] text-ink-500">{recipient.email}</div>}

                          </td>

                          <td className="max-w-0 truncate text-ink-800">{draft.subject||"(no subject)"}</td>

                          <td><StatusPill status={draft.status}/></td>

                          <td className="text-right" onClick={(e)=>e.stopPropagation()}>

                            {canSend ? (

                              <button

                                onClick={()=>approveAndSend(draft)}

                                disabled={sendingDraftId===draft.id}

                                className="btn-ghost btn-sm"

                                title="Send email"

                              >

                                {sendingDraftId===draft.id?<Loader2 className="h-3.5 w-3.5 animate-spin"/>:<Send className="h-3.5 w-3.5"/>}Send

                              </button>

                            ) : (

                              <span className="text-[11.5px] text-ink-400" title={draftBlockReason(draft)}>{draftBlockReason(draft)||"—"}</span>

                            )}

                          </td>

                        </tr>

                      );

                    })}

                    {sortedDrafts.length===0&&(

                      <tr>

                        <td colSpan={4} className="table-empty">No drafts yet. Use “Write email” to create one.</td>

                      </tr>

                    )}

                  </tbody>

                </table>

              </div>

            </Card>

          </div>

        )}

        {view==="inbox"&&(

          <div className="space-y-4">

            <PageHeader title="Inbox" subtitle="Replies pulled from IMAP; read state in your mailbox is untouched." eyebrow="Deliverability">

              <button onClick={syncInboxNow} disabled={inboxBusy || !inbox.configured} className="btn-ghost">

                <RefreshCw className={"h-3.5 w-3.5 "+(inboxBusy ? "animate-spin" : "")}/>{inboxBusy ? "Syncing…" : "Sync now"}

              </button>

            </PageHeader>

            {inboxError && <div className="notice-error">{inboxError}</div>}

            <Card title="Messages" subtitle={inbox.configured?`${inbox.messages.length} stored message(s)`:"Not configured"}>

              {!inbox.configured ? (

                <EmptyState icon={Mail} title="Inbox is not configured" description={imapConfig?.transport==="gmail_api"?"Add the Gmail OAuth credentials to the backend deployment environment.":"Add the mailbox in Settings → Inbox (IMAP), or set IMAP_HOST, IMAP_USER and IMAP_PASS in the environment."}/>

              ) : inbox.messages.length === 0 ? (

                <EmptyState icon={Mail} title="No messages stored yet" description="Use “Sync now” to fetch the newest mail (nothing is marked as read)."/>

              ) : (

                <div className="divide-y divide-ink-100">

                  {inbox.messages.map((m) => (

                    <div key={m.id} className="py-3 first:pt-0 last:pb-0">

                      <div className="flex items-baseline justify-between gap-3">

                        <p className="truncate text-[13px] font-medium text-ink-900">{m.subject}</p>

                        <span className="shrink-0 text-[11px] tabular-nums text-ink-400">{m.received_at ? new Date(m.received_at).toLocaleString() : ""}</span>

                      </div>

                      <p className="truncate text-[12px] text-ink-500">{m.sender}</p>

                      {m.snippet && <p className="mt-1 line-clamp-2 text-[12.5px] text-ink-600">{m.snippet}</p>}

                    </div>

                  ))}

                </div>

              )}

            </Card>

          </div>

        )}

        {view==="verifications"&&(

          <div className="space-y-4">

            <PageHeader title="Verifications" subtitle="Deliverability results per address, refreshed on demand." eyebrow="Deliverability">

              <button onClick={loadVerifications} disabled={verificationLoading} className="btn-primary">

                <RefreshCw className={"h-3.5 w-3.5 "+(verificationLoading ? "animate-spin" : "")}/>Refresh

              </button>

            </PageHeader>

            <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">

              <StatCard label="Total" value={verificationStats.total} icon={Mail} color="blue"/>

              <StatCard label="Deliverable" value={verificationStats.deliverable} icon={CheckCircle} color="green"/>

              <StatCard label="Undeliverable" value={verificationStats.undeliverable} icon={XCircle} color="red"/>

              <StatCard label="Risky" value={verificationStats.risky} icon={AlertTriangle} color="yellow"/>

              <StatCard label="Inconclusive" value={verificationStats.inconclusive} icon={AlertCircle} color="blue"/>

              <StatCard label="Not checked" value={verificationStats.not_checked} icon={Loader2} color="gray"/>

            </div>

            <Card title="Verification results" className="overflow-hidden">

              <div className="mb-3 flex flex-col gap-2 sm:flex-row">

                <div className="relative min-w-0 flex-1">

                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400"/>

                  <input

                    type="text"

                    placeholder="Search emails..."

                    className={inputCls + " pl-9"}

                    value={verifySearch}

                    onChange={e => setVerifySearch(e.target.value)}

                  />

                </div>

                <select

                  className="select w-full sm:w-48"

                  value={verifyFilter}

                  onChange={e => setVerifyFilter(e.target.value)}

                >

                    <option value="all">All statuses</option>

                    <option value="deliverable">Deliverable</option>

                    <option value="undeliverable">Undeliverable</option>

                    <option value="risky">Risky</option>

                    <option value="inconclusive">Inconclusive</option>

                    <option value="not_checked">Not checked</option>

                  </select>

              </div>

              <div className="-mx-5 -mb-4 overflow-x-auto">

                <table className="data-table">

                  <thead>

                    <tr>

                      <th>Email</th>

                      <th>Status</th>

                      <th>Domain</th>

                      <th className="text-center">SMTP</th>

                      <th className="text-center">MX</th>

                      <th className="text-center">Catch-all</th>

                      <th className="text-center">Disposable</th>

                      <th>Last checked</th>

                      <th>Actions</th>

                    </tr>

                  </thead>

                  <tbody>

                    {(() => {

                      const filtered = verifications.filter(v => {

                        const matchFilter = verifyFilter === "all" || v.status === verifyFilter;

                        const matchSearch = !verifySearch || v.email.toLowerCase().includes(verifySearch.toLowerCase());

                        return matchFilter && matchSearch;

                      });

                      if (verificationLoading) {

                        return (

                          <tr>

                            <td colSpan={9}>

                              <div className="flex items-center justify-center gap-2 py-8 text-[13px] text-ink-500">

                                <Loader2 className="h-4 w-4 animate-spin"/>

                                <span>Loading verifications...</span>

                              </div>

                            </td>

                          </tr>

                        );

                      }

                      if (filtered.length === 0) {

                        return (

                          <tr>

                            <td colSpan={9} className="table-empty">No verifications found.</td>

                          </tr>

                        );

                      }

                      return filtered.map(v => (

                        <tr key={v.id}>

                          <td className="max-w-56 truncate font-mono text-[12.5px]">{v.email}</td>

                          <td>{getStatusBadge(v.status)}</td>

                          <td className="max-w-40 truncate text-ink-500">{v.domain || "-"}</td>

                          <td className="text-center">

                            <Pill v={v.smtp_check || "not_checked"}/>

                          </td>

                          <td className="text-center">

                            <Pill v={v.mx_check || "not_checked"}/>

                          </td>

                          <td className="text-center">

                            {v.catch_all ? <span className="font-medium text-warn-600">Yes</span> : <span className="text-ink-500">No</span>}

                          </td>

                          <td className="text-center">

                            {v.disposable ? <span className="font-medium text-danger-600">Yes</span> : <span className="text-ink-500">No</span>}

                          </td>

                          <td className="whitespace-nowrap text-[12px] text-ink-500">

                            {v.last_checked ? new Date(v.last_checked).toLocaleString() : "-"}

                          </td>

                          <td>

                            <div className="flex gap-0.5">

                              <button

                                onClick={() => handleReverify(v)}

                                disabled={verificationLoading}

                                className="icon-btn"

                                title="Re-verify"

                              >

                                <RefreshCw className="h-4 w-4"/>

                              </button>

                              <button

                                onClick={() => handleDeleteVerification(v.id)}

                                className="icon-btn hover:bg-danger-50 hover:text-danger-600"

                                title="Delete"

                              >

                                <Trash2 className="h-4 w-4"/>

                              </button>

                            </div>

                          </td>

                        </tr>

                      ));

                    })()}

                  </tbody>

                </table>

              </div>

            </Card>

          </div>

        )}

        {view==="history"&&(

          <EmailHistoryView state={state} api={api} reload={load} notify={setStatus}/>

        )}

        {view==="automation"&&(

          <AutomationView api={api}/>

        )}

        {view==="experiments"&&(

          <ExperimentsView api={api}/>

        )}

        {view==="team"&&user?.role==="admin"&&(

          <TeamView api={api} currentUserId={user?.id}/>

        )}

        {view==="settings"&&(

          <div className="space-y-4">

            <PageHeader title="Settings" subtitle="Workspace profile, sending identity and automation." eyebrow="Operations"/>

            <div className="grid gap-4 xl:grid-cols-2">

            <Card title="Business profile" subtitle="Used by the AI when personalizing copy">

              <div className="space-y-3">

                <label className="block"><span className="field-label">Goal</span>

                  <input type="text" placeholder="e.g. book 10 demos this month" className={inputCls} value={settingsForm.goal} onChange={e=>updateSettingsField("goal",e.target.value)}/>

                </label>

                <label className="block"><span className="field-label">Business name</span>

                  <input type="text" placeholder="Acme Inc" className={inputCls} value={settingsForm.business_name} onChange={e=>updateSettingsField("business_name",e.target.value)}/>

                </label>

                <label className="block"><span className="field-label">Business offer</span>

                  <input type="text" placeholder="What you sell, in one line" className={inputCls} value={settingsForm.business_offer} onChange={e=>updateSettingsField("business_offer",e.target.value)}/>

                </label>

                <button onClick={saveSettings} disabled={savingSettings} className={btnPrimary}>

                  {savingSettings?"Saving...":"Save settings"}

                </button>

              </div>

            </Card>

            <Card title="Engagement tracking" subtitle="Opt-in open and click tracking">

              <div className="space-y-3">

                <div className="flex items-start justify-between gap-4">

                  <div className="min-w-0">

                    <div className="text-[13px] font-medium text-ink-900">Track opens and clicks</div>

                    <div className="mt-0.5 text-[12px] leading-5 text-ink-500">

                      Off by default. When on, outbound mail gains an HTML alternative with a

                      1×1 open pixel and wrapped links; the plain-text part is unchanged.

                    </div>

                  </div>

                  <button

                    onClick={()=>updateSettingsField("tracking_enabled",!settingsForm.tracking_enabled)}

                    className={settingsForm.tracking_enabled?"btn-ghost":"btn-primary"}

                  >

                    {settingsForm.tracking_enabled?"Disable":"Enable"}

                  </button>

                </div>

                <div className="flex items-center justify-between rounded-lg border border-ink-200 bg-ink-50 px-3 py-2 text-[12px] text-ink-600">

                  <span>Status</span>

                  <span className={"badge "+(settingsForm.tracking_enabled?"border-brand-200 bg-brand-50 text-brand-700":"border-ink-200 bg-ink-100 text-ink-500")}>{settingsForm.tracking_enabled?"On":"Off"}</span>

                </div>

                <p className="text-[12px] text-ink-500">

                  Opens and clicks are recorded per draft and shown in A/B results.

                  Save settings to persist the change.

                </p>

              </div>

            </Card>

            {smtpConfig?.transport==="gmail_api" ? (
            <Card title="Gmail API sending" subtitle="OAuth credentials are supplied by the backend environment">
              <div className="space-y-3">
                {smtpError&&<div className="notice-error">{smtpError}</div>}
                <p className="text-[12px] text-ink-500">
                  Add GMAIL_OAUTH_CLIENT_ID, GMAIL_OAUTH_CLIENT_SECRET, GMAIL_REFRESH_TOKEN, and GMAIL_USER_EMAIL to the backend deployment. OAuth secrets are never displayed here.
                </p>
                <div className="flex flex-wrap gap-2">
                  <button onClick={checkSmtp} disabled={smtpCheck?.checking} className={btnGhost}>
                    {smtpCheck?.checking?"Checking...":"Test Gmail connection"}
                  </button>
                </div>
                {smtpCheck&&smtpCheck.message&&(
                  <p className={"text-[12px] "+(smtpCheck.ok?"text-brand-700":"text-danger-600")}>{smtpCheck.message}</p>
                )}
              </div>
            </Card>
            ) : (
            <Card title="SMTP configuration" subtitle="Credentials used for every send">

              <div className="space-y-3">

                {smtpError&&<div className="notice-error">{smtpError}</div>}

                <label className="block"><span className="field-label">Host</span>

                  <input type="text" placeholder="smtp.example.com" className={inputCls} value={smtp.host} onChange={e=>updateSmtp("host",e.target.value)}/>

                </label>

                <div className="grid gap-3 sm:grid-cols-[100px_1fr]">

                  <label className="block"><span className="field-label">Port</span>

                    <input type="number" placeholder="587" className={inputCls} value={smtp.port} onChange={e=>updateSmtp("port",e.target.value)}/>

                  </label>

                  <label className="block"><span className="field-label">Username</span>

                    <input type="text" placeholder="apikey" className={inputCls} value={smtp.user} onChange={e=>updateSmtp("user",e.target.value)}/>

                  </label>

                </div>

                <label className="block"><span className="field-label">Password</span>

                  <input type="password" placeholder="••••••••" className={inputCls} value={smtp.pass} onChange={e=>updateSmtp("pass",e.target.value)}/>

                </label>

                <label className="block"><span className="field-label">Sender address</span>

                  <input type="text" placeholder="hello@yourdomain.com" className={inputCls} value={smtp.sender} onChange={e=>updateSmtp("sender",e.target.value)}/>

                </label>

                <div className="flex flex-wrap gap-2">

                  <button onClick={checkSmtp} disabled={smtpCheck?.checking} className={btnGhost}>

                    {smtpCheck?.checking?"Checking...":"Test connection"}

                  </button>

                  <button onClick={saveSmtp} className={btnPrimary}>Save SMTP</button>

                </div>

                {smtpCheck&&smtpCheck.message&&(

                  <p className={"text-[12px] "+(smtpCheck.ok?"text-brand-700":"text-danger-600")}>{smtpCheck.message}</p>

                )}

                {smtpConfig?.source==="environment"&&(

                  <p className="text-[12px] text-ink-500">Using the mailbox from the environment. Saving a row here overrides it.</p>

                )}

              </div>

            </Card>
            )}

            {imapConfig?.transport==="gmail_api" ? (
            <Card title="Gmail API inbox" subtitle="Read-only inbox access for reply sync">
              <div className="space-y-3">
                {imapError&&<div className="notice-error">{imapError}</div>}
                <p className="text-[12px] text-ink-500">
                  Inbox access uses the same OAuth credentials as sending. Authorize both gmail.send and gmail.readonly scopes, then add the credentials to the backend deployment environment.
                </p>
                <div className="flex flex-wrap gap-2">
                  <button onClick={checkImap} disabled={imapCheck?.checking} className={btnGhost}>
                    {imapCheck?.checking?"Checking...":"Test Gmail inbox access"}
                  </button>
                </div>
                {imapCheck&&imapCheck.message&&(
                  <p className={"text-[12px] "+(imapCheck.ok?"text-brand-700":"text-danger-600")}>{imapCheck.message}</p>
                )}
              </div>
            </Card>
            ) : (
            <Card title="Inbox (IMAP)" subtitle="Mailbox polled for replies; read state is never changed">

              <div className="space-y-3">

                {imapError&&<div className="notice-error">{imapError}</div>}

                <label className="block"><span className="field-label">Host</span>

                  <input type="text" placeholder="imap.example.com" className={inputCls} value={imap.host} onChange={e=>updateImap("host",e.target.value)}/>

                </label>

                <div className="grid gap-3 sm:grid-cols-[100px_1fr]">

                  <label className="block"><span className="field-label">Port</span>

                    <input type="number" placeholder="993" className={inputCls} value={imap.port} onChange={e=>updateImap("port",e.target.value)}/>

                  </label>

                  <label className="block"><span className="field-label">Username</span>

                    <input type="text" placeholder="you@yourdomain.com" className={inputCls} value={imap.user} onChange={e=>updateImap("user",e.target.value)}/>

                  </label>

                </div>

                <label className="block"><span className="field-label">Password</span>

                  <input type="password" placeholder="••••••••" className={inputCls} value={imap.pass} onChange={e=>updateImap("pass",e.target.value)}/>

                </label>

                <label className="block"><span className="field-label">Folder</span>

                  <input type="text" placeholder="INBOX" className={inputCls} value={imap.folder} onChange={e=>updateImap("folder",e.target.value)}/>

                </label>

                <div className="flex flex-wrap gap-2">

                  <button onClick={checkImap} disabled={imapCheck?.checking} className={btnGhost}>

                    {imapCheck?.checking?"Checking...":"Test connection"}

                  </button>

                  <button onClick={saveImap} className={btnPrimary}>Save IMAP</button>

                </div>

                {imapCheck&&imapCheck.message&&(

                  <p className={"text-[12px] "+(imapCheck.ok?"text-brand-700":"text-danger-600")}>{imapCheck.message}</p>

                )}

                {imapConfig?.source==="environment"&&(

                  <p className="text-[12px] text-ink-500">Using the mailbox from the environment. Saving a row here overrides it.</p>

                )}

              </div>

            </Card>
            )}

            <Card title="Run goal" subtitle="What the next agent run should optimize for">

              <div className="space-y-3">

                <input type="text" placeholder="Enter goal for next run" className={inputCls} value={settingsForm.goal} onChange={e=>updateSettingsField("goal",e.target.value)}/>

                <button onClick={run} className={btnPrimary}>Run now</button>

              </div>

            </Card>

            </div>

          </div>

        )}

        

        {templateComposer&&(

          <div className="modal-backdrop">

            <div className="modal">

              <div className="modal-head">

                <h3 className="modal-title">{editingTemplate && editingTemplate.id ? "Edit template" : "New template"}</h3>

                <button onClick={()=>{setTemplateComposer(false);setEditingTemplate(null);setTemplateError(null);}} className="icon-btn" aria-label="Close"><XCircle className="h-5 w-5"/></button>

              </div>

              <div className="modal-body">

                <label className="field-label">

                  Name

                  <input type="text" className={inputCls+" mt-1"} value={templateForm.name} onChange={e=>setTemplateForm({...templateForm,name:e.target.value})}/>

                </label>

                <label className="field-label">

                  Category

                  <select className={inputCls+" mt-1"} value={templateForm.category} onChange={e=>setTemplateForm({...templateForm,category:e.target.value})}>

                    <option value="intro">intro</option>

                    <option value="followup">followup</option>

                    <option value="reply">reply</option>

                    <option value="outreach">outreach</option>

                    <option value="nurture">nurture</option>

                  </select>

                </label>

                <label className="field-label">

                  Subject

                  <input type="text" className={inputCls+" mt-1"} value={templateForm.subject_template} onChange={e=>setTemplateForm({...templateForm,subject_template:e.target.value})}/>

                </label>

                <label className="field-label">

                  Body

                  <textarea rows={9} className={inputCls+" mt-1 resize-none font-mono text-[12.5px]"} value={templateForm.body_template} onChange={e=>setTemplateForm({...templateForm,body_template:e.target.value})}/>

                </label>

                <label className="mt-1 flex items-center gap-2 text-[13px] text-ink-600">

                  <input type="checkbox" checked={templateForm.is_active} onChange={e=>setTemplateForm({...templateForm,is_active:e.target.checked})}/>

                  Active

                </label>

                {templateError&&<p className="notice-error">{templateError}</p>}

                <div className="modal-foot -mx-5 -mb-4">

                  <button onClick={()=>{setTemplateComposer(false);setEditingTemplate(null);setTemplateError(null);}} className={btnGhost}>Cancel</button>

                  <button onClick={submitTemplate} className={btnPrimary}>{editingTemplate && editingTemplate.id ? "Save template" : "Create template"}</button>

                </div>

              </div>

            </div>

          </div>

        )}

        {composing&&(

          <div className="modal-backdrop">

            <div className="modal">

              <div className="modal-head">

                <h3 className="modal-title">Write email</h3>

                <button onClick={()=>{setComposing(false);setDraftError(null);}} className="icon-btn" aria-label="Close"><XCircle className="h-5 w-5"/></button>

              </div>

              <div className="modal-body">

                <label className="field-label">

                  Recipient

                  <select className={inputCls+" mt-1"} value={composeForm.contact_id} onChange={e=>setComposeForm({...composeForm,contact_id:e.target.value})}>

                    <option value="">Select a contact…</option>

                    {state.contacts.map(c=>(<option key={c.id} value={c.id}>{c.name?`${c.name} <${c.email}>`:c.email}</option>))}

                  </select>

                </label>

                <label className="field-label">

                  Subject

                  <input type="text" className={inputCls+" mt-1"} value={composeForm.subject} onChange={e=>setComposeForm({...composeForm,subject:e.target.value})}/>

                </label>

                <label className="field-label">

                  Body

                  <textarea rows={8} className={inputCls+" mt-1 resize-none"} value={composeForm.body} onChange={e=>setComposeForm({...composeForm,body:e.target.value})}/>

                </label>

                {draftError&&<p className="notice-error">{draftError}</p>}

                <div className="modal-foot -mx-5 -mb-4">

                  <button onClick={()=>{setComposing(false);setDraftError(null);}} className={btnGhost}>Cancel</button>

                  <button onClick={composeSubmit} className={btnPrimary}>Save draft</button>

                </div>

              </div>

            </div>

          </div>

        )}



        {editingId&&!composing&&(()=>{

          const draft=state.drafts.find(d=>d.id===editingId);

          if(!draft)return null;

          const recipient=state.contacts.find(c=>c.id===draft.contact_id);

          return (

            <div className="modal-backdrop">

              <div className="modal">

                <div className="modal-head">

                  <div>

                    <h3 className="modal-title">Edit draft</h3>

                    <p className="mt-0.5 flex items-center gap-2 text-[12px] text-ink-500">

                      {recipient?.email||"Unknown contact"}

                      <StatusPill status={draft.status}/>

                    </p>

                    {draft.error_message&&<p className="mt-1 text-[12px] text-warn-700">{draft.error_message}</p>}

                  </div>

                  <button onClick={()=>{setEditingId(null);setDraftError(null);}} className="icon-btn" aria-label="Close"><XCircle className="h-5 w-5"/></button>

                </div>

                <div className="modal-body">

                  <label className="field-label">

                    Subject

                    <input type="text" className={inputCls+" mt-1"} value={editForm.subject} onChange={e=>setEditForm({...editForm,subject:e.target.value})}/>

                  </label>

                  <label className="field-label">

                    Body

                    <textarea rows={9} className={inputCls+" mt-1 resize-none"} value={editForm.body} onChange={e=>setEditForm({...editForm,body:e.target.value})}/>

                  </label>

                  {draftError&&<p className="notice-error">{draftError}</p>}

                  <div className="modal-foot -mx-5 -mb-4">

                    <button onClick={()=>{setEditingId(null);setDraftError(null);}} className={btnGhost}>Cancel</button>

                    <button onClick={()=>{setEditingId(null);redraft(draft);}} disabled={redraftingId===draft.id} className={btnGhost+" flex items-center gap-1"}>

                      <Sparkles className="h-4 w-4"/>{redraftingId===draft.id?"Redrafting…":"Redraft"}

                    </button>

                    <button onClick={()=>saveEdit(draft)} className={btnPrimary}>Save changes</button>

                  </div>

                </div>

              </div>

            </div>

          );

        })()}



        {/* Verification Progress Modal */}

        {verifyModalOpen && verifyJob && (

          <div className="modal-backdrop">

            <div className="modal max-w-md">

              <div className="modal-head">

                <h3 className="modal-title">Verifying emails</h3>

                <button onClick={() => setVerifyModalOpen(false)} className="icon-btn" aria-label="Close">

                  <XCircle className="h-5 w-5"/>

                </button>

              </div>

              <div className="modal-body space-y-4">

                <div>

                  <div className="mb-1 flex justify-between text-[12.5px] text-ink-600">

                    <span>Progress</span>

                    <span className="tabular-nums">{verifyProgress.processed} / {verifyProgress.total}</span>

                  </div>

                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-100">

                    <div 

                      className="h-full rounded-full bg-brand-500 transition-all duration-300"

                      style={{width: verifyProgress.total > 0 ? `${(verifyProgress.processed / verifyProgress.total) * 100}%` : '0%'}}

                    ></div>

                  </div>

                </div>

                <div className="grid grid-cols-4 gap-2.5 text-center">

                  <div className="rounded-lg border border-brand-100 bg-brand-50 p-3">

                    <div className="text-[20px] font-semibold tabular-nums text-brand-700">{verifyProgress.deliverable}</div>

                    <div className="text-[11px] text-brand-600">Deliverable</div>

                  </div>

                  <div className="rounded-lg border border-danger-100 bg-danger-50 p-3">

                    <div className="text-[20px] font-semibold tabular-nums text-danger-700">{verifyProgress.undeliverable}</div>

                    <div className="text-[11px] text-danger-600">Undeliverable</div>

                  </div>

                  <div className="rounded-lg border border-warn-100 bg-warn-50 p-3">

                    <div className="text-[20px] font-semibold tabular-nums text-warn-700">{verifyProgress.risky}</div>

                    <div className="text-[11px] text-warn-600">Risky</div>

                  </div>

                  <div className="rounded-lg border border-ink-200 bg-ink-50 p-3">

                    <div className="text-[20px] font-semibold tabular-nums text-ink-700">{verifyProgress.inconclusive}</div>

                    <div className="text-[11px] text-ink-500">Inconclusive</div>

                  </div>

                </div>

                <div className="text-[12.5px] text-ink-500">

                  Status: <span className="font-medium capitalize text-ink-800">{verifyJob.status}</span>

                </div>

                {verifyJob.status === "completed" && (

                  <button

                    onClick={() => setVerifyModalOpen(false)}

                    className={btnPrimary + " w-full"}

                  >

                    Close

                  </button>

                )}

                {verifyJob.status === "failed" && (

                  <div className="notice-error">

                    Error: {verifyJob.error || "Unknown error"}

                  </div>

                )}

              </div>

            </div>

          </div>

        )}

        

        {/* Add Contact Modal */}

        {addContactOpen && (

          <div className="modal-backdrop">

            <div className="modal">

              <div className="modal-head">

                <h3 className="modal-title">Add Contact</h3>

                <button onClick={()=>{setAddContactOpen(false);setAddContactForm({email:"",name:"",company:"",role:"",industry:"",notes:"",eligible_to_email:true});}} className="icon-btn" aria-label="Close"><XCircle className="h-5 w-5"/></button>

              </div>

              <div className="modal-body">

                <label className="field-label">

                  Email *

                  <input type="email" className={inputCls+" mt-1"} value={addContactForm.email} onChange={e=>setAddContactForm({...addContactForm,email:e.target.value})} placeholder="contact@example.com"/>

                </label>

                <label className="field-label">

                  Name

                  <input type="text" className={inputCls+" mt-1"} value={addContactForm.name} onChange={e=>setAddContactForm({...addContactForm,name:e.target.value})} placeholder="John Doe"/>

                </label>

                <label className="field-label">

                  Company

                  <input type="text" className={inputCls+" mt-1"} value={addContactForm.company} onChange={e=>setAddContactForm({...addContactForm,company:e.target.value})} placeholder="Acme Corp"/>

                </label>

                <label className="field-label">

                  Role

                  <input type="text" className={inputCls+" mt-1"} value={addContactForm.role} onChange={e=>setAddContactForm({...addContactForm,role:e.target.value})} placeholder="CTO"/>

                </label>

                <label className="field-label">

                  Industry

                  <input type="text" className={inputCls+" mt-1"} value={addContactForm.industry} onChange={e=>setAddContactForm({...addContactForm,industry:e.target.value})} placeholder="Technology"/>

                </label>

                <label className="field-label">

                  Notes

                  <textarea rows={2} className={inputCls+" mt-1 resize-none"} value={addContactForm.notes} onChange={e=>setAddContactForm({...addContactForm,notes:e.target.value})} placeholder="Additional notes..."/>

                </label>

                <label className="flex items-center gap-2 pt-2">

                  <input type="checkbox" checked={addContactForm.eligible_to_email} onChange={e=>setAddContactForm({...addContactForm,eligible_to_email:e.target.checked})} className="checkbox"/>

                  <span className="text-[13px] text-ink-700">Eligible to email</span>

                </label>

                {error && <p className="notice-error">{error}</p>}

                <div className="modal-foot -mx-5 -mb-4">

                  <button onClick={()=>{setAddContactOpen(false);setAddContactForm({email:"",name:"",company:"",role:"",industry:"",notes:"",eligible_to_email:true});setError(null);}} className={btnGhost}>Cancel</button>

                  <button onClick={addContact} className={btnPrimary}>Add Contact</button>

                </div>

              </div>

            </div>

          </div>

        )}

        

        {/* New List Modal */}

        {showListModal && (

          <div className="modal-backdrop">

          <div className="modal max-w-md">
              <div className="modal-head">

                <h3 className="modal-title">New list</h3>

                <button onClick={()=>{setShowListModal(false);setNewListName("");setNewListFolder("");setListError(null);}} className="icon-btn" aria-label="Close"><XCircle className="h-5 w-5"/></button>

              </div>

              <div className="modal-body">

                <label className="field-label">

                  Name

                  <input

                    className={inputCls + " mt-1"}

                    value={newListName}

                    onChange={e=>setNewListName(e.target.value)}

                    onKeyDown={e=>{ if(e.key==="Enter" && newListName.trim()) createList(); }}

                    placeholder="e.g. Q1 prospects"

                    autoFocus

                  />

                </label>

                <label className="field-label">

                  Folder

                  <select

                    className={inputCls + " mt-1"}

                    value={newListFolder}

                    onChange={e=>setNewListFolder(e.target.value)}

                  >

                    <option value="">No folder</option>

                    {folders.map(folder => (

                      <option key={folder.id} value={String(folder.id)}>{folder.name}</option>

                    ))}

                  </select>

                </label>

                {listError && <p className="notice-error">{listError}</p>}

                <div className="modal-foot -mx-5 -mb-4">

                  <button onClick={()=>{setShowListModal(false);setNewListName("");setNewListFolder("");setListError(null);}} className={btnGhost}>Cancel</button>

                  <button onClick={createList} disabled={!newListName.trim()} className={btnPrimary}>Create list</button>

                </div>

              </div>

            </div>

          </div>

        )}

        {/* New Campaign Modal */}
        {showCampaignModal && (
          <div className="modal-backdrop">
            <div className="modal">
              <div className="modal-head">
                <h3 className="modal-title">New campaign</h3>
                <button onClick={()=>{setShowCampaignModal(false);setCampaignError(null);}} className="icon-btn" aria-label="Close"><XCircle className="h-5 w-5"/></button>
              </div>
              <div className="modal-body">
                <label className="field-label">
                  Campaign name *
                  <input className={inputCls+" mt-1"} value={campaignForm.name} onChange={e=>setCampaignForm({...campaignForm,name:e.target.value})} placeholder="e.g. Q4 product launch" autoFocus/>
                </label>
                <label className="field-label">
                  Subject line
                  <input className={inputCls+" mt-1"} value={campaignForm.subject} onChange={e=>setCampaignForm({...campaignForm,subject:e.target.value})} placeholder="Leave empty to use the template subject"/>
                </label>
                <label className="field-label">
                  Preview text
                  <input className={inputCls+" mt-1"} value={campaignForm.preview_text} onChange={e=>setCampaignForm({...campaignForm,preview_text:e.target.value})} placeholder="Shown next to the subject in most inboxes"/>
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <label className="field-label">
                    Send to list
                    <select className={inputCls+" mt-1"} value={campaignForm.list_id} onChange={e=>setCampaignForm({...campaignForm,list_id:e.target.value})}>
                      <option value="">All eligible contacts</option>
                      {lists.map(list=>(
                        <option key={list.id} value={String(list.id)}>{list.name} ({list.total_subscribers ?? list.member_count})</option>
                      ))}
                    </select>
                  </label>
                  <label className="field-label">
                    Template
                    <select className={inputCls+" mt-1"} value={campaignForm.template_id} onChange={e=>setCampaignForm({...campaignForm,template_id:e.target.value})}>
                      <option value="">First active template</option>
                      {templates.map(template=>(
                        <option key={template.id} value={String(template.id)}>{template.name}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <label className="field-label">
                  Schedule (optional)
                  <input type="datetime-local" className={inputCls+" mt-1"} value={campaignForm.scheduled_at} onChange={e=>setCampaignForm({...campaignForm,scheduled_at:e.target.value})}/>
                </label>
                <p className="text-[12px] text-ink-500">Campaigns are created as drafts. Nothing is sent until you press Send, and every send still respects your daily cap.</p>
                {campaignError && <p className="notice-error">{campaignError}</p>}
                <div className="modal-foot -mx-5 -mb-4">
                  <button onClick={()=>{setShowCampaignModal(false);setCampaignError(null);}} className={btnGhost}>Cancel</button>
                  <button onClick={createCampaign} disabled={campaignBusy||!campaignForm.name.trim()} className={btnPrimary}>Create campaign</button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Campaign Stats Modal */}
        {campaignDetail && (
          <div className="modal-backdrop">
            <div className="modal">
              <div className="modal-head">
                <div>
                  <h3 className="modal-title">{campaignDetail.campaign?.name}</h3>
                  <p className="mt-0.5 text-[12px] text-ink-500">{campaignDetail.campaign?.subject || "No subject"}</p>
                </div>
                <button onClick={()=>setCampaignDetail(null)} className="icon-btn" aria-label="Close"><XCircle className="h-5 w-5"/></button>
              </div>
              <div className="modal-body">
                <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                  {[
                    ["Recipients", campaignDetail.stats?.total_recipients],
                    ["Delivered", campaignDetail.stats?.delivered],
                    ["Opened", campaignDetail.stats?.opened],
                    ["Clicked", campaignDetail.stats?.clicked],
                    ["Replied", campaignDetail.stats?.replied],
                    ["Bounced", campaignDetail.stats?.bounced],
                    ["Unsubscribed", campaignDetail.stats?.unsubscribed],
                    ["Open rate", (campaignDetail.stats?.open_rate ?? 0) + "%"],
                  ].map(([label,value])=>(
                    <div key={label} className="rounded-lg border border-ink-200 bg-ink-50 px-3 py-2">
                      <div className="text-[10.5px] font-semibold uppercase tracking-wide text-ink-500">{label}</div>
                      <div className="text-[17px] font-semibold tabular-nums text-ink-900">{value ?? 0}</div>
                    </div>
                  ))}
                </div>
                <div className="mt-1 text-[12px] text-ink-500">
                  Status: <span className="font-medium text-ink-700">{campaignDetail.campaign?.status}</span>
                  {campaignDetail.campaign?.list_name ? <> · List: <span className="font-medium text-ink-700">{campaignDetail.campaign.list_name}</span></> : null}
                </div>
              </div>
              <div className="modal-foot -mx-5 -mb-4">
                <button onClick={()=>setCampaignDetail(null)} className={btnGhost}>Close</button>
              </div>
            </div>
          </div>
        )}

        {/* Confirmation dialog for destructive actions */}

        {confirmState && (

          <div className="modal-backdrop" onClick={()=>setConfirmState(null)}>

            <div className="modal max-w-md" onClick={e=>e.stopPropagation()}>

              <div className="modal-head">

                <h3 className="modal-title">{confirmState.title}</h3>

                <button onClick={()=>setConfirmState(null)} className="icon-btn" aria-label="Close"><XCircle className="h-5 w-5"/></button>

              </div>

              <div className="modal-body">

                <div className="flex items-start gap-3">

                  <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${confirmState.tone==="danger"?"bg-danger-50 text-danger-600":"bg-brand-50 text-brand-700"}`}><AlertTriangle className="h-4 w-4"/></span>

                  <p className="text-[13px] leading-relaxed text-ink-600">{confirmState.message}</p>

                </div>

              </div>

              <div className="modal-foot">

                <button onClick={()=>setConfirmState(null)} className={btnGhost}>Cancel</button>

                <button
                  onClick={async()=>{
                    const action=confirmState.onConfirm;
                    setConfirmState(null);
                    await action?.();
                  }}
                  className={`btn border-transparent text-white ${confirmState.tone==="danger"?"bg-danger-600 hover:bg-danger-700 active:bg-danger-800":"bg-brand-600 hover:bg-brand-700 active:bg-brand-800"}`}
                  autoFocus
                >
                  {confirmState.confirmLabel||"Delete"}
                </button>

              </div>

            </div>

          </div>

        )}

        {/* New Folder Modal */}

        {showFolderModal && (
          <div className="modal-backdrop">

          <div className="modal max-w-md">
              <div className="modal-head">

                <h3 className="modal-title">Create a new folder</h3>

                <button onClick={()=>{setShowFolderModal(false);setNewFolderName("");setFolderError(null);}} className="icon-btn" aria-label="Close"><XCircle className="h-5 w-5"/></button>

              </div>

              <div className="modal-body">

                <label className="field-label">

                  Folder name

                  <input

                    className={inputCls + " mt-1"}

                    value={newFolderName}

                    onChange={e=>setNewFolderName(e.target.value)}

                    onKeyDown={e=>{ if(e.key==="Enter" && newFolderName.trim()) createFolder(); }}

                    placeholder="e.g. Marketing"

                    autoFocus

                  />

                </label>

                <p className="text-[12px] text-ink-500">Folders group your lists. Deleting a folder deletes its lists but never your contacts.</p>

                {folderError && <p className="notice-error">{folderError}</p>}

                <div className="modal-foot -mx-5 -mb-4">

                  <button onClick={()=>{setShowFolderModal(false);setNewFolderName("");setFolderError(null);}} className={btnGhost}>Cancel</button>

                  <button onClick={createFolder} disabled={!newFolderName.trim()} className={btnPrimary}>Create folder</button>

                </div>

              </div>

            </div>

          </div>

        )}

        {/* List Settings Modal */}

        {showListSettings && (

          <div className="modal-backdrop">

            <div className="modal max-w-2xl max-h-[90vh] overflow-y-auto">

              <div className="modal-head">

                <div>

                  <h3 className="modal-title">List settings</h3>

                  <p className="mt-0.5 text-[12px] text-ink-500">{showListSettings.name}</p>

                </div>

                <button onClick={()=>setShowListSettings(null)} className="icon-btn" aria-label="Close"><XCircle className="h-5 w-5"/></button>

              </div>

              <div className="grid gap-3 modal-body sm:grid-cols-2">

                <label className="field-label sm:col-span-2">

                  Description (only visible to you)

                  <textarea rows={2} className={inputCls+" mt-1 resize-none"} value={listSettingsForm.description} onChange={e=>setListSettingsForm({...listSettingsForm,description:e.target.value})} placeholder="Who is in this list and why"/>

                </label>

                <label className="field-label">

                  From name

                  <input className={inputCls+" mt-1"} value={listSettingsForm.from_name} onChange={e=>setListSettingsForm({...listSettingsForm,from_name:e.target.value})} placeholder="Your company"/>

                </label>

                <label className="field-label">

                  From email

                  <input className={inputCls+" mt-1"} value={listSettingsForm.from_email} onChange={e=>setListSettingsForm({...listSettingsForm,from_email:e.target.value})} placeholder="hello@example.com"/>

                </label>

                <label className="field-label">

                  Reply-to

                  <input className={inputCls+" mt-1"} value={listSettingsForm.reply_to} onChange={e=>setListSettingsForm({...listSettingsForm,reply_to:e.target.value})} placeholder="reply@example.com"/>

                </label>

                <label className="field-label">

                  Footer

                  <input className={inputCls+" mt-1"} value={listSettingsForm.footer} onChange={e=>setListSettingsForm({...listSettingsForm,footer:e.target.value})} placeholder="Unsubscribe text"/>

                </label>

                <label className="field-label sm:col-span-2">

                  Header (mirror link block)

                  <textarea rows={2} className={inputCls+" mt-1 resize-none"} value={listSettingsForm.header} onChange={e=>setListSettingsForm({...listSettingsForm,header:e.target.value})} placeholder="Optional header shown above the email"/>

                </label>

                {listError && <p className="notice-error sm:col-span-2">{listError}</p>}

                <div className="modal-foot -mx-5 -mb-4 mt-1 sm:col-span-2">

                  <button disabled={listBusy} onClick={()=>cleanupListMembers(showListSettings.id, "remove-from-other-lists")} className={btnGhost}>Remove from other lists</button>

                  <button disabled={listBusy} onClick={()=>cleanupListMembers(showListSettings.id, "remove-duplicates")} className={btnGhost}>Remove duplicates from this list</button>

                  <button disabled={listBusy} onClick={()=>setShowListSettings(null)} className={btnGhost}>Cancel</button>

                  <button disabled={listBusy} onClick={saveListSettings} className={btnPrimary}>Save</button>

                </div>

              </div>

            </div>

          </div>

        )}

        {/* Rename List Modal */}

        {showRenameList && (

          <div className="modal-backdrop">

          <div className="modal max-w-md">
              <div className="modal-head">

                <h3 className="modal-title">Rename list</h3>

                <button onClick={()=>setShowRenameList(null)} className="icon-btn" aria-label="Close"><XCircle className="h-5 w-5"/></button>

              </div>

              <div className="modal-body">

                <input

                  className={inputCls}

                  value={renameListName}

                  onChange={e=>setRenameListName(e.target.value)}

                  onKeyDown={e=>{ if(e.key==="Enter") renameList(showRenameList.id, renameListName); }}

                  autoFocus

                />

                {listError && <p className="notice-error">{listError}</p>}

                <div className="modal-foot -mx-5 -mb-4">

                  <button onClick={()=>setShowRenameList(null)} className={btnGhost}>Cancel</button>

                  <button onClick={()=>renameList(showRenameList.id, renameListName)} disabled={!renameListName.trim()} className={btnPrimary}>Save</button>

                </div>

              </div>

            </div>

          </div>

        )}

        {/* Move List Modal */}

        {showMoveList && (

          <div className="modal-backdrop">

          <div className="modal max-w-md">
              <div className="modal-head">

                <h3 className="modal-title">Move list to a folder</h3>

                <button onClick={()=>setShowMoveList(null)} className="icon-btn" aria-label="Close"><XCircle className="h-5 w-5"/></button>

              </div>

              <div className="modal-body space-y-2">

                {[{ id: "none", name: "No folder" }, ...folders].map(folder => (

                  <button

                    key={folder.id}

                    onClick={()=>moveList(showMoveList.id, String(folder.id))}

                    className="flex w-full items-center justify-between rounded-lg border border-ink-200 px-3 py-2 text-[13px] text-ink-700 hover:bg-ink-50"

                  >

                    <span>{folder.name}</span>

                    {String(showMoveList.folder_id || "none") === String(folder.id) && <Check className="h-4 w-4 text-brand-600"/>}

                  </button>

                ))}

                {listError && <p className="notice-error">{listError}</p>}

              </div>

            </div>

          </div>

        )}

        {/* Import Contacts Into List Modal */}

        {showListImport && (

          <div className="modal-backdrop">

            <div className="modal max-w-2xl">

              <div className="modal-head">

                <div>

                  <h3 className="modal-title">Import contacts to the list</h3>

                  <p className="mt-0.5 text-[12px] text-ink-500">{showListImport.name}</p>

                </div>

                <button onClick={()=>{setShowListImport(null);setListImportText("");}} className="icon-btn" aria-label="Close"><XCircle className="h-5 w-5"/></button>

              </div>

              <div className="modal-body">

                <p className="text-[12px] text-ink-500">Paste CSV with an <code>email</code> column. Optional: name, company, role, phone, linkedin, notes. Existing contacts are updated and added to this list.</p>

                <textarea

                  rows={10}

                  className={inputCls+" font-mono text-xs"}

                  value={listImportText}

                  onChange={e=>setListImportText(e.target.value)}

                  placeholder={"email,name,company\nada@example.com,Ada,Analytical Engines"}

                />

                {listError && <p className="notice-error">{listError}</p>}

                <div className="modal-foot -mx-5 -mb-4">

                  <button onClick={()=>{setShowListImport(null);setListImportText("");}} className={btnGhost}>Cancel</button>

                  <button onClick={importCsvToList} disabled={listBusy || !listImportText.trim()} className={btnPrimary}>Import</button>

                </div>

              </div>

            </div>

          </div>

        )}

        {/* Add Contacts To List Modal */}

        {showAddToList && (

          <div className="modal-backdrop">

            <div className="modal max-w-2xl">

              <div className="modal-head">

                <div>

                  <h3 className="modal-title">Add contacts to {showAddToList.name}</h3>

                  <p className="mt-0.5 text-[12px] text-ink-500">{addToListIds.length} selected</p>

                </div>

                <button onClick={()=>{setShowAddToList(null);setAddToListIds([]);}} className="icon-btn" aria-label="Close"><XCircle className="h-5 w-5"/></button>

              </div>

              <div className="modal-body space-y-2">

                <div className="max-h-64 divide-y divide-ink-100 overflow-y-auto rounded-lg border border-ink-200">

                  {(state.contacts || []).map(contact => {

                    const checked = addToListIds.includes(contact.id);

                    return (

                      <label key={contact.id} className="flex cursor-pointer items-center gap-3 px-3 py-2 text-[13px] hover:bg-ink-50">

                        <input

                          type="checkbox"

                          checked={checked}

                          onChange={()=>setAddToListIds(prev => checked ? prev.filter(id => id !== contact.id) : [...prev, contact.id])}

                          className="checkbox"

                        />

                        <span className="font-medium text-ink-900">{contact.name || contact.email}</span>

                        <span className="truncate text-ink-500">{contact.email}</span>

                      </label>

                    );

                  })}

                  {!(state.contacts || []).length && <p className="px-3 py-6 text-center text-[13px] text-ink-500">No contacts yet.</p>}

                </div>

                {listError && <p className="notice-error">{listError}</p>}

                <div className="modal-foot -mx-5 -mb-4">

                  <button onClick={()=>{setShowAddToList(null);setAddToListIds([]);}} className={btnGhost}>Cancel</button>

                  <button onClick={addSelectedContactsToList} disabled={listBusy || !addToListIds.length} className={btnPrimary}>Add {addToListIds.length || ""} contact(s)</button>

                </div>

              </div>

            </div>

          </div>

        )}

        

        {/* Send Selected Modal */}

        {sendSelectedOpen && (

          <div className="modal-backdrop">

          <div className="modal max-w-md">
              <div className="modal-head">

                <h3 className="modal-title">Send Emails to Selected Contacts</h3>

                <button onClick={()=>{setSendSelectedOpen(false);setSendSelectedTemplate(null);}} className="icon-btn" aria-label="Close"><XCircle className="h-5 w-5"/></button>

              </div>

              <div className="modal-body">

                <p className="mb-4 text-[13px] text-ink-700">

                  You have <strong className="font-semibold">{selectedContacts.size} contact(s)</strong> selected.

                  {templates.find(t => t.id === sendSelectedTemplate) && (

                    <span> Using template: <strong className="font-semibold">{templates.find(t => t.id === sendSelectedTemplate).name}</strong></span>

                  )}

                </p>

                {sendSelectedSmtpReady ? (

                  <div className="notice-warn mb-4">

                    <p className="text-[12px]">This will send actual emails through the configured mail transport. Only eligible contacts will receive emails.</p>

                  </div>

                ) : (

                  <div className="notice-error mb-4">

                    <p className="text-[12px]">Mail is not configured. Set up the selected mail transport in Settings.</p>

                  </div>

                )}

                <div className="modal-foot -mx-5 -mb-4">

                  <button onClick={()=>{setSendSelectedOpen(false);setSendSelectedTemplate(null);}} className={btnGhost}>Cancel</button>

                  <button 

                    onClick={confirmSendSelected} 

                    disabled={!sendSelectedSmtpReady}

                    className={btnPrimary + " " + (!sendSelectedSmtpReady ? "opacity-50 disabled:cursor-not-allowed" : "")}

                  >

                    Send Emails

                  </button>

                </div>

              </div>

            </div>

          </div>

        )}

      </div></div></main>
      </div>
    </>);

}