import { useState, useEffect } from 'react';
import { 
  Mail, Users, FileText, Inbox, Settings, Play, BarChart3, 
  Activity, Monitor, Send, AlertCircle, Upload, Pencil, Sparkles, 
  PenLine, Brain, Copy, Trash2, Shield, CheckCircle, XCircle, 
  AlertTriangle, Loader2, RefreshCw, Filter, Search, Plus
} from 'lucide-react';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:3000';

const api = async (path, opts = {}) => {
  const response = await fetch(`${API_URL}${path}`, {
    ...opts,
    headers: { "Content-Type": "application/json", ...opts.headers },
  });
  const body = await response.text();
  let data;
  try {
    data = body ? JSON.parse(body) : null;
  } catch {
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
    throw new Error(`Invalid JSON response (${response.status})`);
  }
  if (!response.ok) {
    const errorMsg = (data && data.detail) || (body && body.trim()) || `Request failed (${response.status})`;
    throw new Error(errorMsg);
  }
  return data;
};

const inputCls = "w-full px-3 py-2 border border-gray-200 rounded-md text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:border-gray-400";
const btnGhost = "px-3 py-1.5 rounded-md border border-gray-200 bg-white text-gray-700 text-sm font-medium hover:bg-gray-50 disabled:opacity-50";
const btnPrimary = "px-3 py-1.5 rounded-md bg-gray-900 text-white text-sm font-medium hover:bg-black disabled:opacity-50";

function NavItem({icon:Icon, label, active, onClick}){
  return (
    <button onClick={onClick} className={"w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors "+(active?"bg-gray-900 text-white":"text-gray-500 hover:text-gray-900 hover:bg-gray-50")}>
      <Icon className="w-5 h-5 shrink-0"/><span className="text-[15px] font-medium">{label}</span>
    </button>
  );
}

function Card({title, children, action}){
  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900">{title}</h3>{action&&<div className="flex gap-2">{action}</div>}</div>
      <div className="p-6">{children}</div>
    </div>
  );
}

function StatCard({label,value,icon:Icon,color="blue"}){
  const STAT_COLORS = { blue: "text-blue-600", green: "text-green-600", red: "text-red-600", yellow: "text-yellow-600", gray: "text-gray-600" };
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs text-gray-500 uppercase tracking-wider">{label}</div>
          <div className={"text-2xl font-semibold "+(STAT_COLORS[color]||STAT_COLORS.blue)}>{value}</div>
        </div>
        <div className="w-10 h-10 rounded-lg border border-gray-200 bg-gray-50 flex items-center justify-center text-gray-400"><Icon className="w-5 h-5"/></div>
      </div>
    </div>
  );
}

function Pill({v}){
  return <span className="px-2.5 py-1 rounded-full text-xs border border-gray-200 text-gray-700 bg-white">{v}</span>;
}

function ErrorDisplay({err,onRetry}){
  return (
    <div className="flex flex-col items-center justify-center h-full text-center p-8">
      <AlertCircle className="w-12 h-12 text-red-600 mb-4"/>
      <h3 className="text-lg font-semibold text-[#111] mb-2">UI Error</h3>
      <p className="text-[#777] text-sm mb-6 max-w-md">{err}</p>
      <button onClick={onRetry} className="px-4 py-2 rounded-md bg-[#111] text-white text-sm font-medium hover:bg-black">Retry</button>
    </div>
  );
}

export default function App(){
  const [view,setView]=useState("overview");
  const [state,setState]=useState({contacts:[],drafts:[],events:[],logs:[],tools:[],analytics:{}});
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState(null);

  const load=useCallback(async({quiet=false}={})=>{
    try{
      const s=await api("/api/contacts");
      setState(normalizeState(s));
      setError(null);
    }catch(e){
      if(!quiet)setError(e?.message||String(e));
    }finally{
      if(!quiet)setLoading(false);
    }
  },[]);

  useEffect(()=>{
    load();
  },[load]);

  const normalizeState = (s) => ({
    ...s,
    contacts: Array.isArray(s) ? s : [],
    drafts: Array.isArray(s?.drafts) ? s.drafts : [],
    events: Array.isArray(s?.events) ? s.events : [],
    logs: Array.isArray(s?.logs) ? s.logs : [],
    tools: Array.isArray(s?.tools) ? s.tools : [],
    analytics: s?.analytics || {},
  });

  const items=[
    {id:"overview",icon:BarChart3,label:"Overview"},
    {id:"contacts",icon:Users,label:"Contacts"},
    {id:"drafts",icon:FileText,label:"Drafts"},
    {id:"templates",icon:PenLine,label:"Templates"},
    {id:"inbox",icon:Inbox,label:"Inbox"},
    {id:"settings",icon:Settings,label:"Settings"},
  ];

  if(error){
    return (
      <div className="h-screen bg-[#fafafa] text-[#111] flex items-center justify-center">
        <ErrorDisplay err={error} onRetry={load}/>
      </div>
    );
  }

  if(loading){
    return (
      <div className="h-screen bg-[#fafafa] text-[#111] flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-4 border-[#e4e4e4] border-t-[#111] rounded-full animate-spin"></div>
          <span className="text-[#777] text-sm">Loading Email Orchestrator...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-[#fafafa] text-[#111] selection:bg-[#111] selection:text-white flex overflow-hidden">
      <aside className="w-[320px] max-md:w-16 shrink-0 border-r border-[#e4e4e4] flex flex-col bg-white">
        <div className="px-5 py-7 border-b border-[#e4e4e4] flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-[#111] text-white flex items-center justify-center overflow-hidden shrink-0">
            <Mail className="w-5 h-5"/>
          </div>
          <span className="font-bold text-[17px] tracking-tight max-md:hidden">Email Orchestrator</span>
        </div>
        <nav className="flex-1 px-4 py-5 space-y-1">
          {items.map(it=>(
            <NavItem key={it.id} icon={it.icon} label={<span className="max-md:hidden">{it.label}</span>} active={view===it.id} onClick={()=>setView(it.id)}/>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 flex flex-col overflow-hidden">
        <header className="h-[72px] shrink-0 border-b border-[#e4e4e4] flex items-center justify-between px-6 max-md:px-3 bg-white">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-md bg-[#fafafa] border border-[#e4e4e4] flex items-center justify-center text-[#777]"><Activity className="w-4 h-4"/></div>
            <h1 className="text-base font-semibold tracking-tight capitalize">{view}</h1>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={load} aria-label="Refresh dashboard" className="w-9 h-9 rounded-lg bg-white border border-[#e4e4e4] flex items-center justify-center text-[#777] hover:text-[#111] transition-colors"><Monitor className="w-4 h-4"/></button>
          </div>
        </header>
        <div className="flex-1 overflow-y-auto p-6 max-md:p-3">
          {view==="overview"&&(
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <StatCard label="Contacts" value={state.contacts?.length||0} icon={Users}/>
                <StatCard label="Drafts" value={state.drafts?.length||0} icon={FileText}/>
                <StatCard label="Templates" value={state.templates?.length||0} icon={PenLine}/>
              </div>
              <div className="mt-6 grid gap-4">
                <Card title="Recent Activity">
                  <div className="space-y-5">
                    <section>
                      <h3 className="text-xs font-semibold text-gray-700 mb-3">Activity history</h3>
                      <div className="space-y-3 max-h-48 overflow-y-auto">
                        {state.logs?.slice(0,10).map(log=>(
                          <div key={log.id} className="text-xs border-b border-[#e4e4e4] pb-2 last:border-0 last:pb-0">
                            <div className="flex items-start gap-2">
                              <span className="text-[#777]">{new Date(log.timestamp).toLocaleString()}</span>
                              <span className="text-[#111]">{log.message}</span>
                            </div>
                          </div>
                        ))}
                        {(!state.logs||state.logs.length===0)&&
                          <p className="text-xs text-[#777]">No recent activity.</p>
                        }
                      </div>
                    </section>
                  </div>
                </Card>
              </div>
            </>
          )}
          {view==="contacts"&&(
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <h2 className="text-sm font-semibold flex items-center gap-2"><Users className="w-4 h-4"/>Contacts</h2>
                <div className="flex items-center gap-2 flex-wrap">
                  <button onClick={()=>setAddContactOpen(true)} className="px-3 py-1.5 rounded-md bg-[#111] text-white text-xs font-medium hover:bg-black flex items-center gap-1"><Plus className="w-4 h-4 mr-1"/>Add Contact</button>
                  <input type="file" accept=".csv" ref={fileInputRef} onChange={e=>{importCsv(e.target.files[0]);e.target.value="";}} className="hidden"/>
                  <button onClick={()=>fileInputRef.current?.click()} className="px-3 py-1.5 rounded-md bg-[#111] text-white text-xs font-medium hover:bg-black"><Upload className="w-4 h-4 mr-1"/>Import CSV</button>
                </div>
              </div>
              <Card title="Contacts">
                <div className="overflow-y-auto max-h-96">
                  <table className="w-full text-sm">
                    <thead className="bg-[#f5f5f5]">
                      <tr>
                        <th className="px-3 py-2 text-left">Name</th>
                        <th className="px-3 py-2 text-left">Email</th>
                        <th className="px-3 py-2 text-left">Company</th>
                        <th className="px-3 py-2 text-center">Eligible</th>
                      </tr>
                    </thead>
                    <tbody>
                      {state.contacts?.map(contact=>(
                        <tr key={contact.id} className="border-b border-[#e4e4e4] hover:bg-[#fafafa]">
                          <td className="px-3 py-2 truncate max-w-40">{contact.name||"-"}</td>
                          <td className="px-3 py-2 truncate max-w-56">{contact.email||"-"}</td>
                          <td className="px-3 py-2 truncate max-w-40">{contact.company||"-"}</td>
                          <td className="px-3 py-2 text-center">
                            <span className={contact.eligibleToEmail ? "text-green-600" : "text-red-600"}>
                              {contact.eligibleToEmail ? "Yes" : "No"}
                            </span>
                          </td>
                        </tr>
                      ))}
                      {(!state.contacts||state.contacts.length===0)&&(
                        <tr>
                          <td colSpan={4} className="px-3 py-2 text-center text-[#777]">No contacts found.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}