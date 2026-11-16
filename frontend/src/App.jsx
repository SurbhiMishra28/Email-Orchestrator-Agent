import { useState, useEffect, useCallback, useRef, Fragment } from "react";
import { Mail, Users, FileText, Inbox, Settings, Play, BarChart3, Activity, Monitor, Send, AlertCircle, Upload, Pencil, Sparkles, PenLine, Brain, Copy, Trash2, Shield, CheckCircle, XCircle, AlertTriangle, Loader2, RefreshCw, Filter, Search, Plus } from "lucide-react";

const api = async (path, opts = {}) => {
  const response = await fetch(path, {
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

const normalizeState = (s) => ({
  ...s,
  contacts: Array.isArray(s?.contacts) ? s.contacts : [],
  drafts: Array.isArray(s?.drafts) ? s.drafts : [],
  events: Array.isArray(s?.events) ? s.events : [],
  logs: Array.isArray(s?.logs) ? s.logs : [],
  tools: Array.isArray(s?.tools) ? s.tools : [],
  analytics: s?.analytics || {},
});

const inputCls = "w-full px-3 py-2 border border-gray-200 rounded-md text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:border-gray-400";
const btnGhost = "px-3 py-1.5 rounded-md border border-gray-200 bg-white text-gray-700 text-sm font-medium hover:bg-gray-50 disabled:opacity-50";
const btnPrimary = "px-3 py-1.5 rounded-md bg-gray-900 text-white text-sm font-medium hover:bg-black disabled:opacity-50";

// static class map so Tailwind can see every color at build time
const STAT_COLORS = {
  blue: "text-blue-600",
  green: "text-green-600",
  red: "text-red-600",
  yellow: "text-yellow-600",
  gray: "text-gray-600",
};

function NavItem({icon:Icon,label,active,onClick}){
  return (
    <button onClick={onClick} className={"w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors "+(active?"bg-gray-900 text-white":"text-gray-500 hover:text-gray-900 hover:bg-gray-50")}>
      <Icon className="w-5 h-5 shrink-0"/><span className="text-[15px] font-medium">{label}</span>
    </button>
  );
}

const STATUS_STYLES = {
  sent: "text-gray-600 border-gray-300",
  blocked: "text-gray-600 border-gray-300",
  failed: "text-red-600 border-red-300",
  draft: "text-gray-500 border-gray-300",
  sending: "text-blue-600 border-blue-300",
};

function StatusPill({status="draft"}){
  const key=String(status||"draft").toLowerCase();
  return (
    <span className={"inline-flex items-center rounded-full border bg-white px-3 py-0.5 text-xs "+(STATUS_STYLES[key]||STATUS_STYLES.draft)}>
      {key}
    </span>
  );
}

function Card({title,children,action}){
  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900">{title}</h3>{action&&<div className="flex gap-2">{action}</div>}</div>
      <div className="p-6">{children}</div>
    </div>
  );
}

function StatCard({label,value,icon:Icon,color="blue"}){
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
  const [smtp,setSmtp]=useState({host:"",port:"",user:"",pass:"",sender:""});
  const [smtpConfig,setSmtpConfig]=useState(null);
  const [smtpCheck,setSmtpCheck]=useState(null);
  const [smtpDirty,setSmtpDirty]=useState(false);
  const [smtpError,setSmtpError]=useState(null);
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
  const [settingsForm,setSettingsForm]=useState({goal:"",business_name:"",business_offer:""});
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
  const [addContactOpen, setAddContactOpen] = useState(false);
  const [addContactForm, setAddContactForm] = useState({email:"",name:"",company:"",role:"",industry:"",notes:"",eligible_to_email:true});
  const [sendSelectedOpen, setSendSelectedOpen] = useState(false);
  const [sendSelectedTemplate, setSendSelectedTemplate] = useState(null);
  const [sendSelectedSmtpReady, setSendSelectedSmtpReady] = useState(false);

  // Reply analyzer state
  const [replyAnalyzeOpen, setReplyAnalyzeOpen] = useState(false);
  const [replyAnalyzeSubject, setReplyAnalyzeSubject] = useState("");
  const [replyAnalyzeBody, setReplyAnalyzeBody] = useState("");
  const [replyAnalyzeSender, setReplyAnalyzeSender] = useState("");
  const [replyAnalyzeContact, setReplyAnalyzeContact] = useState(null);
  const [replyAnalyzeResult, setReplyAnalyzeResult] = useState(null);
  const [replyAnalyzeLoading, setReplyAnalyzeLoading] = useState(false);
  const [replyAnalyzeError, setReplyAnalyzeError] = useState(null);

  // Run orchestrator (manual trigger)
  const run = async () => {
    try {
      const result = await api("/api/run", {
        method: "POST",
        body: JSON.stringify({ goal: settingsForm.goal || undefined })
      });
      setStatus(`Queue run: ${result.result?.sent || 0} sent, ${result.result?.failed || 0} failed`);
      setTimeout(() => setStatus(null), 5000);
      await load();
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  // Reply analyzer handler
  const analyzeReply = async () => {
    if (!replyAnalyzeBody.trim()) return;
    
    setReplyAnalyzeLoading(true);
    setReplyAnalyzeError(null);
    setReplyAnalyzeResult(null);
    
    try {
      const result = await api("/api/replies/analyze", {
        method: "POST",
        body: JSON.stringify({
          subject: replyAnalyzeSubject,
          body: replyAnalyzeBody,
          sender_email: replyAnalyzeSender,
          contact_id: replyAnalyzeContact
        })
      });
      setReplyAnalyzeResult(result);
    } catch (e) {
      setReplyAnalyzeError(e?.message || "Failed to analyze reply");
    } finally {
      setReplyAnalyzeLoading(false);
    }
  };

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
    let active=true;
    const controller=new AbortController();
    const fetchState=async(quiet=false)=>{
      try{
        const s=await api("/api/state",{signal:controller.signal});
        if(active){setState(normalizeState(s));setError(null);}
      }catch(e){
        if(active&&!quiet&&e?.name!=="AbortError")setError(e?.message||String(e));
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
  },[]);

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
    loadTemplates();
  }, []);

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
    await api(`/api/templates/${tid}`, { method: "DELETE" });
    await loadTemplates();
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
    loadVerificationsIfNeeded();
  }, [loadVerificationsIfNeeded]);

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
    if (view === "inbox") loadInbox();
  }, [view, loadInbox]);

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
    // Check SMTP readiness properly when opening the modal
    // smtpReady might be false due to race condition - re-check synchronously
    const smtpIsReady = Boolean(
      smtpConfig?.configured &&
      !smtpDirty &&
      smtpCheck?.ok &&
      (!smtpConfig.authentication_configured || smtpCheck?.authenticated)
    );
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
        } else {
          setStatus(result.message || "No emails sent");
        }
        setTimeout(() => setStatus(null), 3000);
      }, 1000);
      await load();
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
      const filtered = state.contacts
        .filter(c => !contactsSearch || c.email.toLowerCase().includes(contactsSearch.toLowerCase()) || (c.name||"").toLowerCase().includes(contactsSearch.toLowerCase()))
        .map(c => c.id);
      setSelectedContacts(new Set(filtered));
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

  const getStatusBadge = (status) => {
    const styles = {
      deliverable: "bg-green-100 text-green-700 border-green-200",
      undeliverable: "bg-red-100 text-red-700 border-red-200",
      risky: "bg-yellow-100 text-yellow-700 border-yellow-200",
      inconclusive: "bg-gray-100 text-gray-700 border-gray-200",
      not_checked: "bg-gray-100 text-gray-500 border-gray-200"
    };
    const icons = {
      deliverable: <CheckCircle className="w-3 h-3 mr-1"/>,
      undeliverable: <XCircle className="w-3 h-3 mr-1"/>,
      risky: <AlertTriangle className="w-3 h-3 mr-1"/>,
      inconclusive: <AlertCircle className="w-3 h-3 mr-1"/>,
      not_checked: <Loader2 className="w-3 h-3 mr-1 animate-spin"/>
    };
    const label = status.charAt(0).toUpperCase() + status.slice(1).replace("_", " ");
    return (
      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${styles[status] || styles.not_checked}`}>
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
    if (!window.confirm("Delete this verification record?")) return;
    try {
      await api(`/api/verifications/${id}`, { method: "DELETE" });
      await loadVerifications();
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  // keep the settings form in sync with the server until the user edits it
  useEffect(()=>{
    if(!settingsDirty&&state.settings){
      setSettingsForm({
        goal:state.settings.goal||"",
        business_name:state.settings.business_name||"",
        business_offer:state.settings.business_offer||"",
      });
    }
  },[state.settings,settingsDirty]);

  useEffect(()=>{
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
        if (config?.configured && config?.authentication_configured) {
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
      
      // Fetch health status
      try {
        const h = await api("/health");
        if(active) setHealth(h);
      } catch({}) {/* ignore health check errors */}
    })();
    
    return ()=>{active=false;};
  },[]);

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
      setStatus(r.message||`Imported ${r.imported} contact(s)`);setTimeout(()=>setStatus(null),4000);
      await load();
    }catch(e){setError(e?.message||String(e));}
    finally{setCsvBusy(false);}
  };

  const updateEligibility=async(contact,eligible)=>{
    if(eligible&&!window.confirm(`Confirm ${contact.email} has opted in or is otherwise eligible to receive email.`))return;
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
      setStatus("Your draft is queued for approval");setTimeout(()=>setStatus(null),2500);
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
    const port=smtp.port?Number(smtp.port):587;
    if(!Number.isInteger(port)||port<1||port>65535){
      setSmtpCheck({ok:false,message:"SMTP port must be an integer between 1 and 65535."});
      return;
    }
    try{
      setSmtpCheck({checking:true,message:"Connecting to SMTP server..."});
      const result=await api("/api/smtp/test",{method:"POST",body:JSON.stringify({
        host:smtp.host.trim()||undefined,
        port,
        user:smtp.user.trim()||undefined,
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
    if(!smtpConfig?.configured||smtpDirty||!smtpCheck?.ok||
      (smtpConfig.authentication_configured&&!smtpCheck.authenticated)){
      setDraftError("Configure and save SMTP in Settings, then successfully test the connection before sending.");
      return;
    }
    if(!window.confirm(`Send "${draft.subject}" to ${recipient.email} now using SMTP?`))return;

    setSendingDraftId(draft.id);
    setDraftError(null);
    try{
      await api(`/api/drafts/${draft.id}/send`,{method:"POST"});
      const refreshed=normalizeState(await api("/api/state"));
      setState(refreshed);
      const updated=refreshed.drafts.find((item)=>item.id===draft.id);
      if(updated?.status==="sent"){
        setStatus("Email sent via SMTP");
        setTimeout(()=>setStatus(null),2500);
      }else{
        setDraftError(`Draft was not marked sent (current status: ${updated?.status||"unknown"}). Check SMTP settings and server logs before retrying.`);
      }
    }catch(e){
      setDraftError(e?.message||String(e));
    }finally{
      setSendingDraftId(null);
    }
  };

  const smtpReady=Boolean(
    smtpConfig?.configured &&
    !smtpDirty &&
    smtpCheck?.ok &&
    (!smtpConfig.authentication_configured || smtpCheck?.authenticated === true)
  );

  const draftBlockReason=(draft)=>{
    if(draft.status==="sent") return "Already sent";
    if(!smtpConfig?.configured) return "SMTP not configured";
    if(smtpDirty) return "Save SMTP changes";
    if(!smtpCheck?.ok) return "Test SMTP in Settings";
    if(smtpConfig.authentication_configured&&smtpCheck?.authenticated !== true) return "SMTP auth not verified";
    const recipient=state.contacts.find(c=>c.id===draft.contact_id);
    if(!recipient) return "Recipient missing";
    if(!recipient.eligible_to_email) return "Recipient not eligible";
    return "";
  };

  const sortedDrafts=[...state.drafts].sort((a,b)=>(b.id||0)-(a.id||0));

  const items=[
    {id:"overview",icon:BarChart3,label:"Overview"},
    {id:"agents",icon:Brain,label:"Agents"},
    {id:"contacts",icon:Users,label:"Contacts"},
    {id:"drafts",icon:FileText,label:"Drafts"},
    {id:"templates",icon:PenLine,label:"Templates"},
    {id:"inbox",icon:Inbox,label:"Inbox"},
    {id:"verifications",icon:Shield,label:"Verifications"},
    {id:"settings",icon:Settings,label:"Settings"},
  ];

  const systemLive=health?.status==="healthy";

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
        <div className="p-5 max-md:hidden border-t border-[#e4e4e4]">
          <div className="text-xs text-[#777] mb-2">System</div>
          <div className="flex items-center justify-between px-3 py-2.5 rounded-md bg-[#f5f5f5] border border-[#e4e4e4]">
            <div className="flex items-center gap-2">
              <span className={"w-2 h-2 rounded-full "+(systemLive?"bg-green-500":"bg-amber-500")}></span>
              <span className="text-sm font-medium">{systemLive?"Live":"Degraded"}</span>
            </div>
            <span className="text-xs text-[#777]">{new Date().toLocaleTimeString()}</span>
          </div>
          {status&&<div className="mt-2 text-xs text-[#2563eb] px-1">{status}</div>}
        </div>
      </aside>
      <main className="min-w-0 flex-1 flex flex-col overflow-hidden">
        <header className="h-[72px] shrink-0 border-b border-[#e4e4e4] flex items-center justify-between px-6 max-md:px-3 bg-white">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-md bg-[#fafafa] border border-[#e4e4e4] flex items-center justify-center text-[#777]"><Activity className="w-4 h-4"/></div>
            <h1 className="text-base font-semibold tracking-tight capitalize">{view}</h1>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={run} className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[#111] text-white text-sm font-medium hover:bg-black transition-colors"><Play className="w-4 h-4"/>Run</button>
            <button onClick={load} aria-label="Refresh dashboard" className="w-9 h-9 rounded-lg bg-white border border-[#e4e4e4] flex items-center justify-center text-[#777] hover:text-[#111] transition-colors"><Monitor className="w-4 h-4"/></button>
          </div>
        </header>
        <div className="flex-1 overflow-y-auto p-6 max-md:p-3">
          {view==="overview"&&(
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <StatCard label="Contacts" value={state.contacts?.length||0} icon={Users}/>
                <StatCard label="Drafts" value={state.drafts?.length||0} icon={FileText}/>
                <StatCard label="Replies" value={(state.events||[]).filter(e=>e.type==="reply_event").length} icon={Mail}/>
              </div>
              <div className="mt-6 grid gap-4">
                <Card title="Recent Activity">
                  <div className="space-y-3 max-h-64 overflow-y-auto">
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
                </Card>
              </div>
            </>
          )}
          {view==="templates"&&(
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">Email Templates</h2>
                <button onClick={()=>{setEditingTemplate(null);setTemplateForm({name:"",category:"intro",subject_template:"",body_template:"",variables:{},tags:[],is_active:true});setComposing(true);}} className="px-3 py-1.5 rounded-md bg-[#111] text-white text-xs font-medium hover:bg-black"><PenLine className="w-4 h-4 mr-1"/>New Template</button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {templates.map(template=>(
                  <div key={template.id} className="border border-[#e4e4e4] rounded-md bg-white p-4">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-sm font-semibold">{template.name}</h3>
                      <div className="flex gap-1">
                        <button onClick={()=>handleEditTemplate(template)} className="p-1 rounded text-[#777] hover:text-[#111]"><Pencil className="w-4 h-4"/></button>
                        <button onClick={()=>duplicateTemplate(template.id)} className="p-1 rounded text-[#777] hover:text-[#111]"><Copy className="w-4 h-4"/></button>
                        <button onClick={()=>deleteTemplate(template.id)} className="p-1 rounded text-[#777] hover:text-red-600"><Trash2 className="w-4 h-4"/></button>
                      </div>
                    </div>
                    <p className="text-xs text-[#777] mb-2 line-clamp-2">{template.subject_template}</p>
                    <div className="flex flex-wrap gap-1 mb-2">
                      {template.tags?.map(tag=><Pill key={tag} v={tag}/>)}
                      <Pill v={template.category}/>
                    </div>
                    <p className="text-[10px] text-[#aaa]">Variables: {Object.keys(template.variables||{}).join(", ")||"none"}</p>
                  </div>
                ))}
                {templates.length===0&&(
                  <p className="text-[#777] text-sm col-span-full">No templates found. Create your first template!</p>
                )}
              </div>
            </div>
          )}
          {view==="agents"&&(
          <div className="space-y-4">
            <h2 className="text-sm font-semibold flex items-center gap-2"><Brain className="w-4 h-4"/>Agents</h2>
            <p className="text-sm text-[#777]">
              Agents coordinate the email orchestration workflow. When NVIDIA LLM is configured, 
              they can personalize emails and generate content. Otherwise, built-in templates are used.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <Card title="Email Drafting">
                <p className="text-sm text-[#777] mb-2">Personalize and draft emails to contacts.</p>
              </Card>
              <Card title="SMTP Sending">
                <p className="text-sm text-[#777] mb-2">Send emails through configured SMTP relay.</p>
              </Card>
              <Card title="Follow-ups">
                <p className="text-sm text-[#777] mb-2">Every 6 hours, drafts a day-3 and day-5 follow-up for sent emails. Drafts wait for approval; nothing is sent automatically.</p>
              </Card>
              <Card title="Inbox Sync">
                <p className="text-sm text-[#777] mb-2">Polls IMAP for new mail and stores sender, subject and a short snippet. Read state in your mailbox is unchanged.</p>
              </Card>
              <Card title="Reply Classification">
                <p className="text-sm text-[#777] mb-2">Process and classify incoming replies.</p>
                <button 
                  onClick={() => {
                    setReplyAnalyzeOpen(true);
                    setReplyAnalyzeResult(null);
                    setReplyAnalyzeError(null);
                  }}
                  className="px-3 py-1.5 rounded-md bg-[#111] text-white text-xs font-medium hover:bg-black"
                >
                  Analyze Reply
                </button>
              </Card>
              <Card title="Calendar Booking">
                <p className="text-sm text-[#777] mb-2">Not connected. No calendar integration is installed, so this is not automated.</p>
              </Card>
              <Card title="Memory">
                <p className="text-sm text-[#777] mb-2">Not implemented. Interaction history is stored as events, but the agent does not use it yet.</p>
              </Card>
            </div>
          </div>
        )}
        {view==="contacts"&&(
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <h2 className="text-sm font-semibold flex items-center gap-2"><Users className="w-4 h-4"/>Contacts</h2>
              <div className="flex items-center gap-2 flex-wrap">
                <button onClick={()=>{setAddContactOpen(true);setAddContactForm({email:"",name:"",company:"",role:"",industry:"",notes:"",eligible_to_email:true});}} className="px-3 py-1.5 rounded-md bg-[#111] text-white text-xs font-medium hover:bg-black flex items-center gap-1"><Plus className="w-4 h-4 mr-1"/>Add Contact</button>
                <input type="file" accept=".csv" ref={fileInputRef} onChange={e=>{importCsv(e.target.files[0]);e.target.value="";}} className="hidden"/>
                <button onClick={()=>fileInputRef.current?.click()} className="px-3 py-1.5 rounded-md bg-[#111] text-white text-xs font-medium hover:bg-black"><Upload className="w-4 h-4 mr-1"/>Import CSV</button>
                {selectedContacts.size > 0 && (
                  <>
                    <button onClick={()=>{setSelectedContacts(new Set());setSelectAllContacts(false);}} className="px-2.5 py-1.5 rounded-md border border-gray-300 bg-white text-xs font-medium text-gray-700 hover:bg-gray-50">Clear</button>
                    <div className="relative">
                      <select
                        onChange={e => {
                          const templateId = e.target.value ? Number(e.target.value) : null;
                          if (templateId) handleSendSelected(templateId);
                          e.target.value = "";
                        }}
                        className="appearance-none w-40 px-3 py-1.5 rounded-md border border-gray-300 bg-white text-xs font-medium text-gray-700 hover:bg-gray-50 pr-8"
                      >
                        <option value="">Send via...</option>
                        {templates.map(t => (
                          <option key={t.id} value={t.id}>{t.name}</option>
                        ))}
                      </select>
                      <Send className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500 pointer-events-none"/>
                    </div>
                  </>
                )}
              </div>
            </div>
            <Card title="Contact List">
              <div className="flex gap-3 mb-3">
                <div className="flex-1 relative min-w-0">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#777] w-4 h-4"/>
                  <input
                    type="text"
                    placeholder="Search contacts..."
                    className={inputCls + " pl-10 w-full"}
                    value={contactsSearch}
                    onChange={e => setContactsSearch(e.target.value)}
                  />
                </div>
              </div>
              <div className="overflow-y-auto max-h-96">
                <table className="w-full text-sm">
                  <thead className="bg-[#f5f5f5]">
                    <tr>
                      <th className="px-3 py-2 text-center w-10 min-w-10"><input type="checkbox" checked={selectAllContacts} onChange={toggleSelectAll} className="rounded border-[#e4e4e4] w-4 h-4"/></th>
                      <th className="px-3 py-2 text-left w-40 min-w-40">Name</th>
                      <th className="px-3 py-2 text-left w-56 min-w-56">Email</th>
                      <th className="px-3 py-2 text-left w-40 min-w-40">Company</th>
                      <th className="px-3 py-2 text-center w-32 min-w-32">Eligible</th>
                      <th className="px-3 py-2 text-center w-16 min-w-16">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.contacts?.filter(c => !contactsSearch || c.email.toLowerCase().includes(contactsSearch.toLowerCase()) || (c.name||"").toLowerCase().includes(contactsSearch.toLowerCase())).map(contact=>(
                      <tr key={contact.id} className="border-b border-[#e4e4e4] hover:bg-[#fafafa]">
                        <td className="px-3 py-2 text-center">
                          <input type="checkbox" checked={selectedContacts.has(contact.id)} onChange={()=>toggleContactSelection(contact.id)} className="rounded border-[#e4e4e4] w-4 h-4"/>
                        </td>
                        <td className="px-3 py-2 truncate max-w-40">{contact.name||"-"}</td>
                        <td className="px-3 py-2 truncate max-w-56">{contact.email||"-"}</td>
                        <td className="px-3 py-2 truncate max-w-40">{contact.company||"-"}</td>
                        <td className="px-3 py-2 text-center">
                          <label className="flex items-center justify-center gap-2">
                            <input type="checkbox" checked={contact.eligible_to_email||false} onChange={e=>updateEligibility(contact,e.target.checked)} disabled={eligibilityBusyId===contact.id} className="w-4 h-4 rounded border-[#e4e4e4]"/>
                            <span className="text-xs text-[#777]">{eligibilityBusyId===contact.id?"...":(contact.eligible_to_email?"Yes":"No")}</span>
                          </label>
                        </td>
                        <td className="px-3 py-2 text-center">
                          <button
                            onClick={()=>{setComposeForm({contact_id:String(contact.id),subject:"",body:""});setDraftError(null);setComposing(true);}}
                            className="p-1.5 rounded text-[#777] hover:text-[#111] hover:bg-[#f5f5f5] transition-colors"
                            title="Write email"
                          >
                            <PenLine className="w-4 h-4"/>
                          </button>
                        </td>
                      </tr>
                    ))}
                    {(!state.contacts||state.contacts.length===0)&&(
                      <tr>
                        <td colSpan={6} className="px-3 py-2 text-center text-[#777]">No contacts found.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}
        {view==="drafts"&&(
          <div className="mx-auto max-w-[1440px]">
            <section className="rounded-lg border border-gray-200 bg-white">
              <div className="flex items-center justify-between gap-3 border-b border-gray-200 px-6 py-5">
                <h2 className="text-lg font-semibold text-gray-900">Drafts</h2>
                <button
                  onClick={()=>{setComposeForm({contact_id:"",subject:"",body:""});setDraftError(null);setComposing(true);}}
                  className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3.5 py-2 text-sm font-medium text-gray-800 transition-colors hover:bg-gray-50"
                >
                  <PenLine className="h-4 w-4"/>Write email
                </button>
              </div>
              <div className="px-6 py-5">
                <p className="text-sm text-gray-500">Sending is a real email action. Review the recipient and confirm before each send.</p>
                {!smtpReady&&(
                  <div className="mt-4 flex flex-col gap-2 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-gray-800 sm:flex-row sm:items-center sm:justify-between">
                    <span>{smtpConfig?.configured ? "Save and test the SMTP connection in Settings to enable sending." : "Add SMTP settings in Settings to enable sending."}</span>
                    <button type="button" onClick={()=>setView("settings")} className="shrink-0 text-sm underline underline-offset-2 hover:text-black">Open SMTP Settings</button>
                  </div>
                )}
                {draftError&&<p className="mt-3 text-sm text-red-600">{draftError}</p>}
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-[15px]">
                    <thead>
                      <tr className="border-b border-gray-200 text-left text-sm text-gray-500">
                        <th className="w-[34%] py-3 pr-4 font-normal">To</th>
                        <th className="w-[38%] py-3 pr-4 font-normal">Subject</th>
                        <th className="w-[14%] py-3 pr-4 font-normal">Status</th>
                        <th className="w-[14%] py-3 font-normal">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedDrafts.map(draft=>{
                        const recipient=state.contacts.find(c=>c.id===draft.contact_id);
                        const canSend=draft.status!=="sent"&&smtpReady&&Boolean(recipient?.eligible_to_email);
                        return (
                          <tr key={draft.id} onClick={()=>startEdit(draft)} className="cursor-pointer border-b border-gray-200 last:border-0 hover:bg-gray-50">
                            <td className="py-4 pr-4 align-top">
                              <div className="font-medium text-gray-900">{recipient?.name||recipient?.email||"Unknown contact"}</div>
                              {recipient?.email&&<div className="mt-0.5 text-xs text-gray-500">{recipient.email}</div>}
                            </td>
                            <td className="max-w-0 truncate py-4 pr-4 align-top text-gray-800">{draft.subject||"(no subject)"}</td>
                            <td className="py-4 pr-4 align-top"><StatusPill status={draft.status}/></td>
                            <td className="py-4 align-top" onClick={(e)=>e.stopPropagation()}>
                              {canSend ? (
                                <button
                                  onClick={()=>approveAndSend(draft)}
                                  disabled={sendingDraftId===draft.id}
                                  className="rounded p-1.5 text-gray-600 transition-colors hover:bg-gray-100 hover:text-black disabled:opacity-50"
                                  title="Send email"
                                >
                                  {sendingDraftId===draft.id?<Loader2 className="h-4 w-4 animate-spin"/>:<Send className="h-4 w-4"/>}
                                </button>
                              ) : (
                                <span className="text-xs text-gray-500" title={draftBlockReason(draft)}>{draftBlockReason(draft)||"—"}</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                      {sortedDrafts.length===0&&(
                        <tr>
                          <td colSpan={4} className="py-10 text-center text-sm text-gray-500">No drafts yet. Use “Write email” to create one.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          </div>
        )}
        {view==="inbox"&&(
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <h2 className="text-sm font-semibold flex items-center gap-2"><Inbox className="w-4 h-4"/> Inbox</h2>
              <button onClick={syncInboxNow} disabled={inboxBusy || !inbox.configured} className={btnGhost + " flex items-center gap-1 disabled:cursor-not-allowed"}>
                <RefreshCw className={`w-4 h-4 ${inboxBusy ? "animate-spin" : ""}`}/>{inboxBusy ? "Syncing…" : "Sync now"}
              </button>
            </div>
            {inboxError && (
              <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{inboxError}</div>
            )}
            <Card title="Messages">
              {!inbox.configured ? (
                <div className="text-center py-8 text-gray-500">
                  <Mail className="w-8 h-8 mx-auto mb-2"/>
                  <p className="text-sm">IMAP is not configured. Add IMAP_HOST, IMAP_USER and IMAP_PASS to your environment, then reload.</p>
                </div>
              ) : inbox.messages.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <Mail className="w-8 h-8 mx-auto mb-2"/>
                  <p className="text-sm">No messages stored yet. Use “Sync now” to fetch the newest mail (nothing is marked as read).</p>
                </div>
              ) : (
                <div className="divide-y divide-gray-100">
                  {inbox.messages.map((m) => (
                    <div key={m.id} className="py-3 first:pt-0 last:pb-0">
                      <div className="flex items-baseline justify-between gap-3">
                        <p className="text-sm font-medium text-gray-900 truncate">{m.subject}</p>
                        <span className="text-xs text-gray-400 shrink-0">{m.received_at ? new Date(m.received_at).toLocaleString() : ""}</span>
                      </div>
                      <p className="text-xs text-gray-500 truncate">{m.sender}</p>
                      {m.snippet && <p className="text-sm text-gray-600 mt-1 line-clamp-2">{m.snippet}</p>}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}
        {view==="verifications"&&(
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <h2 className="text-sm font-semibold flex items-center gap-2"><Shield className="w-4 h-4"/>Email Verifications</h2>
              <button onClick={loadVerifications} disabled={verificationLoading} className="px-3 py-1.5 rounded-md bg-[#111] text-white text-xs font-medium hover:bg-black disabled:opacity-50 flex items-center gap-1">
                <RefreshCw className={`w-4 h-4 ${verificationLoading ? 'animate-spin' : ''}`}/>Refresh
              </button>
            </div>
            
            {/* Stats Cards */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              <StatCard label="Total" value={verificationStats.total} icon={Mail} color="blue"/>
              <StatCard label="Deliverable" value={verificationStats.deliverable} icon={CheckCircle} color="green"/>
              <StatCard label="Undeliverable" value={verificationStats.undeliverable} icon={XCircle} color="red"/>
              <StatCard label="Risky" value={verificationStats.risky} icon={AlertTriangle} color="yellow"/>
              <StatCard label="Inconclusive" value={verificationStats.inconclusive} icon={AlertCircle} color="blue"/>
              <StatCard label="Not Checked" value={verificationStats.not_checked} icon={Loader2} color="gray"/>
            </div>
            
            {/* Filters & Search */}
            <Card title="Verification Results">
              <div className="flex flex-col sm:flex-row gap-3 mb-4">
                <div className="flex-1 relative min-w-0">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#777] w-4 h-4"/>
                  <input
                    type="text"
                    placeholder="Search emails..."
                    className={inputCls + " pl-10 w-full"}
                    value={verifySearch}
                    onChange={e => setVerifySearch(e.target.value)}
                  />
                </div>
                <div className="w-full sm:w-auto">
                  <select
                    className={inputCls + " w-full sm:w-auto"}
                    value={verifyFilter}
                    onChange={e => setVerifyFilter(e.target.value)}
                  >
                    <option value="all">All Statuses</option>
                    <option value="deliverable">Deliverable</option>
                    <option value="undeliverable">Undeliverable</option>
                    <option value="risky">Risky</option>
                    <option value="inconclusive">Inconclusive</option>
                    <option value="not_checked">Not Checked</option>
                  </select>
                </div>
              </div>
              
              {/* Results Table */}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-[#f5f5f5]">
                    <tr>
                      <th className="px-3 py-2 text-left w-56 min-w-56">Email</th>
                      <th className="px-3 py-2 text-left w-32 min-w-32">Status</th>
                      <th className="px-3 py-2 text-left w-40 min-w-40">Domain</th>
                      <th className="px-3 py-2 text-center w-28 min-w-28">SMTP</th>
                      <th className="px-3 py-2 text-center w-28 min-w-28">MX</th>
                      <th className="px-3 py-2 text-center w-28 min-w-28">Catch-all</th>
                      <th className="px-3 py-2 text-center w-28 min-w-28">Disposable</th>
                      <th className="px-3 py-2 text-left w-44 min-w-44">Last Checked</th>
                      <th className="px-3 py-2 text-left w-28 min-w-28">Actions</th>
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
                            <td colSpan={9} className="px-3 py-8 text-center text-[#777]">
                              <div className="flex items-center justify-center gap-2">
                                <Loader2 className="w-5 h-5 animate-spin"/>
                                <span>Loading verifications...</span>
                              </div>
                            </td>
                          </tr>
                        );
                      }
                      
                      if (filtered.length === 0) {
                        return (
                          <tr>
                            <td colSpan={9} className="px-3 py-8 text-center text-[#777]">No verifications found.</td>
                          </tr>
                        );
                      }
                      
                      return filtered.map(v => (
                        <tr key={v.id} className="border-b border-[#e4e4e4] hover:bg-[#fafafa]">
                          <td className="px-3 py-2 font-mono text-sm truncate max-w-56">{v.email}</td>
                          <td className="px-3 py-2">{getStatusBadge(v.status)}</td>
                          <td className="px-3 py-2 text-[#777] truncate max-w-40">{v.domain || "-"}</td>
                          <td className="px-3 py-2 text-center">
                            <Pill v={v.smtp_check || "not_checked"}/>
                          </td>
                          <td className="px-3 py-2 text-center">
                            <Pill v={v.mx_check || "not_checked"}/>
                          </td>
                          <td className="px-3 py-2 text-center">
                            {v.catch_all ? <span className="text-yellow-600 font-medium">Yes</span> : <span className="text-green-600">No</span>}
                          </td>
                          <td className="px-3 py-2 text-center">
                            {v.disposable ? <span className="text-red-600 font-medium">Yes</span> : <span className="text-green-600">No</span>}
                          </td>
                          <td className="px-3 py-2 text-[#777] whitespace-nowrap">
                            {v.last_checked ? new Date(v.last_checked).toLocaleString() : "-"}
                          </td>
                          <td className="px-3 py-2">
                            <div className="flex gap-1">
                              <button
                                onClick={() => handleReverify(v)}
                                disabled={verificationLoading}
                                className="p-1.5 rounded text-[#777] hover:text-[#111] hover:bg-[#f5f5f5] disabled:opacity-50 transition-colors"
                                title="Re-verify"
                              >
                                <RefreshCw className="w-4 h-4"/>
                              </button>
                              <button
                                onClick={() => handleDeleteVerification(v.id)}
                                className="p-1.5 rounded text-[#777] hover:text-red-600 hover:bg-[#f5f5f5] transition-colors"
                                title="Delete"
                              >
                                <Trash2 className="w-4 h-4"/>
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
        {view==="settings"&&(
          <div className="space-y-4">
            <h2 className="text-sm font-semibold flex items-center gap-2"><Settings className="w-4 h-4"/>Settings</h2>
            <Card title="Business Profile">
              <div className="space-y-3">
                <input type="text" placeholder="Goal" className={inputCls} value={settingsForm.goal} onChange={e=>updateSettingsField("goal",e.target.value)}/>
                <input type="text" placeholder="Business Name" className={inputCls} value={settingsForm.business_name} onChange={e=>updateSettingsField("business_name",e.target.value)}/>
                <input type="text" placeholder="Business Offer" className={inputCls} value={settingsForm.business_offer} onChange={e=>updateSettingsField("business_offer",e.target.value)}/>
                <button onClick={saveSettings} disabled={savingSettings} className={btnPrimary}>
                  {savingSettings?"Saving...":"Save Settings"}
                </button>
              </div>
            </Card>
            <Card title="SMTP Configuration">
              <div className="space-y-3">
                {smtpError&&<p className="text-xs text-red-600">{smtpError}</p>}
                <input type="text" placeholder="SMTP Host" className={inputCls} value={smtp.host} onChange={e=>updateSmtp("host",e.target.value)}/>
                <div className="flex gap-2">
                  <input type="number" placeholder="Port" className={inputCls+" w-20"} value={smtp.port} onChange={e=>updateSmtp("port",e.target.value)}/>
                  <input type="text" placeholder="Username" className={inputCls} value={smtp.user} onChange={e=>updateSmtp("user",e.target.value)}/>
                </div>
                <input type="password" placeholder="Password" className={inputCls} value={smtp.pass} onChange={e=>updateSmtp("pass",e.target.value)}/>
                <input type="text" placeholder="Sender" className={inputCls} value={smtp.sender} onChange={e=>updateSmtp("sender",e.target.value)}/>
                <div className="flex gap-2">
                  <button onClick={checkSmtp} disabled={smtpCheck?.checking} className={btnGhost}>
                    {smtpCheck?.checking?"Checking...":"Test Connection"}
                  </button>
                  <button onClick={saveSmtp} className={btnPrimary}>Save SMTP</button>
                </div>
                {smtpCheck&&smtpCheck.message&&(
                  <p className={"text-xs "+(smtpCheck.ok?"text-green-600":"text-red-600")}>{smtpCheck.message}</p>
                )}
              </div>
            </Card>
            <Card title="Run Goal">
              <div className="space-y-3">
                <input type="text" placeholder="Enter goal for next run" className={inputCls} value={settingsForm.goal} onChange={e=>updateSettingsField("goal",e.target.value)}/>
                <button onClick={run} className={btnPrimary}>Run</button>
              </div>
            </Card>
          </div>
        )}
        
        {composing&&(
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="w-full max-w-lg rounded-lg bg-white shadow-xl">
              <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
                <h3 className="text-base font-semibold text-gray-900">Write email</h3>
                <button onClick={()=>{setComposing(false);setDraftError(null);}} className="text-gray-400 hover:text-gray-700" aria-label="Close"><XCircle className="h-5 w-5"/></button>
              </div>
              <div className="space-y-3 px-6 py-5">
                <label className="block text-sm text-gray-600">
                  Recipient
                  <select className={inputCls+" mt-1"} value={composeForm.contact_id} onChange={e=>setComposeForm({...composeForm,contact_id:e.target.value})}>
                    <option value="">Select a contact…</option>
                    {state.contacts.map(c=>(<option key={c.id} value={c.id}>{c.name?`${c.name} <${c.email}>`:c.email}</option>))}
                  </select>
                </label>
                <label className="block text-sm text-gray-600">
                  Subject
                  <input type="text" className={inputCls+" mt-1"} value={composeForm.subject} onChange={e=>setComposeForm({...composeForm,subject:e.target.value})}/>
                </label>
                <label className="block text-sm text-gray-600">
                  Body
                  <textarea rows={8} className={inputCls+" mt-1 resize-none"} value={composeForm.body} onChange={e=>setComposeForm({...composeForm,body:e.target.value})}/>
                </label>
                {draftError&&<p className="text-sm text-red-600">{draftError}</p>}
                <div className="flex justify-end gap-2 pt-1">
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
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
              <div className="w-full max-w-lg rounded-lg bg-white shadow-xl">
                <div className="flex items-start justify-between border-b border-gray-200 px-6 py-4">
                  <div>
                    <h3 className="text-base font-semibold text-gray-900">Edit draft</h3>
                    <p className="mt-0.5 flex items-center gap-2 text-xs text-gray-500">
                      {recipient?.email||"Unknown contact"}
                      <StatusPill status={draft.status}/>
                    </p>
                    {draft.error_message&&<p className="mt-1 text-xs text-amber-700">{draft.error_message}</p>}
                  </div>
                  <button onClick={()=>{setEditingId(null);setDraftError(null);}} className="text-gray-400 hover:text-gray-700" aria-label="Close"><XCircle className="h-5 w-5"/></button>
                </div>
                <div className="space-y-3 px-6 py-5">
                  <label className="block text-sm text-gray-600">
                    Subject
                    <input type="text" className={inputCls+" mt-1"} value={editForm.subject} onChange={e=>setEditForm({...editForm,subject:e.target.value})}/>
                  </label>
                  <label className="block text-sm text-gray-600">
                    Body
                    <textarea rows={9} className={inputCls+" mt-1 resize-none"} value={editForm.body} onChange={e=>setEditForm({...editForm,body:e.target.value})}/>
                  </label>
                  {draftError&&<p className="text-sm text-red-600">{draftError}</p>}
                  <div className="flex flex-wrap justify-end gap-2 pt-1">
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
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-md w-full">
              <div className="p-5 border-b border-[#e4e4e4] flex items-center justify-between">
                <h3 className="text-lg font-semibold">Verifying Emails</h3>
                <button onClick={() => setVerifyModalOpen(false)} className="text-[#777] hover:text-[#111]">
                  <XCircle className="w-5 h-5"/>
                </button>
              </div>
              <div className="p-5 space-y-4">
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span>Progress</span>
                    <span>{verifyProgress.processed} / {verifyProgress.total}</span>
                  </div>
                  <div className="w-full h-2 bg-[#e4e4e4] rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-[#2563eb] transition-all duration-300"
                      style={{width: verifyProgress.total > 0 ? `${(verifyProgress.processed / verifyProgress.total) * 100}%` : '0%'}}
                    ></div>
                  </div>
                </div>
                
                <div className="grid grid-cols-4 gap-3 text-center">
                  <div className="p-3 rounded-md bg-green-50 border border-green-100">
                    <div className="text-2xl font-bold text-green-700">{verifyProgress.deliverable}</div>
                    <div className="text-xs text-green-600">Deliverable</div>
                  </div>
                  <div className="p-3 rounded-md bg-red-50 border border-red-100">
                    <div className="text-2xl font-bold text-red-700">{verifyProgress.undeliverable}</div>
                    <div className="text-xs text-red-600">Undeliverable</div>
                  </div>
                  <div className="p-3 rounded-md bg-yellow-50 border border-yellow-100">
                    <div className="text-2xl font-bold text-yellow-700">{verifyProgress.risky}</div>
                    <div className="text-xs text-yellow-600">Risky</div>
                  </div>
                  <div className="p-3 rounded-md bg-gray-50 border border-gray-100">
                    <div className="text-2xl font-bold text-gray-700">{verifyProgress.inconclusive}</div>
                    <div className="text-xs text-gray-600">Inconclusive</div>
                  </div>
                </div>
                
                <div className="text-sm text-[#777]">
                  Status: <span className="font-medium capitalize">{verifyJob.status}</span>
                </div>
                
                {verifyJob.status === "completed" && (
                  <button
                    onClick={() => setVerifyModalOpen(false)}
                    className="w-full px-3 py-2 rounded-md bg-[#111] text-white text-sm font-medium hover:bg-black"
                  >
                    Close
                  </button>
                )}
                {verifyJob.status === "failed" && (
                  <div className="text-xs text-red-600 p-2 bg-red-50 rounded">
                    Error: {verifyJob.error || "Unknown error"}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
        
        {/* Add Contact Modal */}
        {addContactOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="w-full max-w-lg rounded-lg bg-white shadow-xl">
              <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
                <h3 className="text-base font-semibold text-gray-900">Add Contact</h3>
                <button onClick={()=>{setAddContactOpen(false);setAddContactForm({email:"",name:"",company:"",role:"",industry:"",notes:"",eligible_to_email:true});}} className="text-gray-400 hover:text-gray-700" aria-label="Close"><XCircle className="h-5 w-5"/></button>
              </div>
              <div className="space-y-3 px-6 py-5">
                <label className="block text-sm text-gray-600">
                  Email *
                  <input type="email" className={inputCls+" mt-1"} value={addContactForm.email} onChange={e=>setAddContactForm({...addContactForm,email:e.target.value})} placeholder="contact@example.com"/>
                </label>
                <label className="block text-sm text-gray-600">
                  Name
                  <input type="text" className={inputCls+" mt-1"} value={addContactForm.name} onChange={e=>setAddContactForm({...addContactForm,name:e.target.value})} placeholder="John Doe"/>
                </label>
                <label className="block text-sm text-gray-600">
                  Company
                  <input type="text" className={inputCls+" mt-1"} value={addContactForm.company} onChange={e=>setAddContactForm({...addContactForm,company:e.target.value})} placeholder="Acme Corp"/>
                </label>
                <label className="block text-sm text-gray-600">
                  Role
                  <input type="text" className={inputCls+" mt-1"} value={addContactForm.role} onChange={e=>setAddContactForm({...addContactForm,role:e.target.value})} placeholder="CTO"/>
                </label>
                <label className="block text-sm text-gray-600">
                  Industry
                  <input type="text" className={inputCls+" mt-1"} value={addContactForm.industry} onChange={e=>setAddContactForm({...addContactForm,industry:e.target.value})} placeholder="Technology"/>
                </label>
                <label className="block text-sm text-gray-600">
                  Notes
                  <textarea rows={2} className={inputCls+" mt-1 resize-none"} value={addContactForm.notes} onChange={e=>setAddContactForm({...addContactForm,notes:e.target.value})} placeholder="Additional notes..."/>
                </label>
                <label className="flex items-center gap-2 pt-2">
                  <input type="checkbox" checked={addContactForm.eligible_to_email} onChange={e=>setAddContactForm({...addContactForm,eligible_to_email:e.target.checked})} className="rounded border-gray-300"/>
                  <span className="text-sm text-gray-600">Eligible to email</span>
                </label>
                {error && <p className="text-sm text-red-600">{error}</p>}
                <div className="flex justify-end gap-2 pt-1">
                  <button onClick={()=>{setAddContactOpen(false);setAddContactForm({email:"",name:"",company:"",role:"",industry:"",notes:"",eligible_to_email:true});setError(null);}} className={btnGhost}>Cancel</button>
                  <button onClick={addContact} className={btnPrimary}>Add Contact</button>
                </div>
              </div>
            </div>
          </div>
        )}
        
        {/* Send Selected Modal */}
        {sendSelectedOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="w-full max-w-md rounded-lg bg-white shadow-xl">
              <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
                <h3 className="text-base font-semibold text-gray-900">Send Emails to Selected Contacts</h3>
                <button onClick={()=>{setSendSelectedOpen(false);setSendSelectedTemplate(null);}} className="text-gray-400 hover:text-gray-700" aria-label="Close"><XCircle className="h-5 w-5"/></button>
              </div>
              <div className="p-6">
                <p className="text-sm text-gray-600 mb-4">
                  You have <strong>{selectedContacts.size} contact(s)</strong> selected.
                  {templates.find(t => t.id === sendSelectedTemplate) && (
                    <span> Using template: <strong>{templates.find(t => t.id === sendSelectedTemplate).name}</strong></span>
                  )}
                </p>
                {sendSelectedSmtpReady ? (
                  <div className="bg-amber-50 border border-amber-200 rounded-md p-3 mb-4">
                    <p className="text-xs text-amber-800">This will send actual emails via SMTP. Only eligible contacts will receive emails.</p>
                  </div>
                ) : (
                  <div className="bg-red-50 border border-red-200 rounded-md p-3 mb-4">
                    <p className="text-xs text-red-800">SMTP is not configured. Please configure SMTP in Settings first.</p>
                  </div>
                )}
                <div className="flex justify-end gap-2">
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
        
        {/* Reply Analyzer Modal */}
        {replyAnalyzeOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="w-full max-w-2xl rounded-lg bg-white shadow-xl">
              <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
                <h3 className="text-base font-semibold text-gray-900">Analyze Email Reply</h3>
                <button 
                  onClick={() => {
                    setReplyAnalyzeOpen(false);
                    setReplyAnalyzeSubject("");
                    setReplyAnalyzeBody("");
                    setReplyAnalyzeSender("");
                    setReplyAnalyzeContact(null);
                    setReplyAnalyzeResult(null);
                    setReplyAnalyzeError(null);
                  }} 
                  className="text-gray-400 hover:text-gray-700" 
                  aria-label="Close"
                >
                  <XCircle className="h-5 w-5"/>
                </button>
              </div>
              <div className="p-6">
                {/* Input Section */}
                {!replyAnalyzeResult && (
                  <div className="space-y-4">
                    <div>
                      <label className="text-xs text-gray-600 mb-1 block">Subject</label>
                      <input
                        type="text"
                        value={replyAnalyzeSubject}
                        onChange={e => setReplyAnalyzeSubject(e.target.value)}
                        placeholder="Re: Your email subject"
                        className={inputCls}
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-600 mb-1 block">Sender Email</label>
                      <input
                        type="email"
                        value={replyAnalyzeSender}
                        onChange={e => setReplyAnalyzeSender(e.target.value)}
                        placeholder="sender@example.com"
                        className={inputCls}
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-600 mb-1 block">Reply Body</label>
                      <textarea
                        value={replyAnalyzeBody}
                        onChange={e => setReplyAnalyzeBody(e.target.value)}
                        placeholder="Paste the reply email here..."
                        rows={6}
                        className={inputCls + " resize-y"}
                      />
                    </div>
                    {replyAnalyzeError && (
                      <p className="text-sm text-red-600">{replyAnalyzeError}</p>
                    )}
                    <div className="flex justify-end gap-2 pt-2">
                      <button 
                        onClick={() => setReplyAnalyzeOpen(false)} 
                        className={btnGhost}
                      >
                        Cancel
                      </button>
                      <button 
                        onClick={analyzeReply} 
                        disabled={replyAnalyzeLoading || !replyAnalyzeBody.trim()}
                        className={btnPrimary}
                      >
                        {replyAnalyzeLoading ? (
                          <span className="flex items-center gap-2">
                            <Loader2 className="w-4 h-4 animate-spin"/>
                            Analyzing...
                          </span>
                        ) : (
                          "Analyze Reply"
                        )}
                      </button>
                    </div>
                  </div>
                )}
                
                {/* Results Section */}
                {replyAnalyzeResult && (
                  <div className="space-y-4">
                    <div className="bg-gray-50 rounded-md p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <Shield className="w-4 h-4 text-gray-600"/>
                        <span className="text-xs text-gray-500 uppercase font-medium">Classification Result</span>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                          <span className="text-xs text-gray-500">Reply Type</span>
                          <span className="text-sm font-medium text-gray-900 block mt-1">
                            {replyAnalyzeResult.reply_type.replace('_', ' ').toUpperCase()}
                          </span>
                        </div>
                        <div>
                          <span className="text-xs text-gray-500">Sentiment</span>
                          <span className="text-sm font-medium block mt-1">
                            {replyAnalyzeResult.sentiment.charAt(0).toUpperCase() + replyAnalyzeResult.sentiment.slice(1)}
                          </span>
                        </div>
                        <div>
                          <span className="text-xs text-gray-500">Confidence</span>
                          <span className="text-sm font-medium text-gray-900 block mt-1">
                            {Math.round(replyAnalyzeResult.confidence * 100)}%
                          </span>
                        </div>
                        <div>
                          <span className="text-xs text-gray-500">Suggested Action</span>
                          <span className="text-sm font-medium text-gray-900 block mt-1">
                            {replyAnalyzeResult.suggested_action.replace('_', ' ').toUpperCase()}
                          </span>
                        </div>
                      </div>
                      {replyAnalyzeResult.key_points?.length > 0 && (
                        <div className="mt-3">
                          <span className="text-xs text-gray-500 mb-1 block">Key Points</span>
                          <ul className="text-xs text-gray-600 space-y-1">
                            {replyAnalyzeResult.key_points.map((point, i) => (
                              <li key={i}>• {point}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {replyAnalyzeResult.needs_human_review && (
                        <div className="mt-3 p-2 bg-amber-100 border border-amber-200 rounded">
                          <span className="text-xs text-amber-800">⚠️ Requires human review</span>
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => {
                        setReplyAnalyzeSubject(replyAnalyzeResult.reply_type); // Just for demo
                        setReplyAnalyzeResult(null);
                      }}
                      className={btnGhost}
                    >
                      Analyze Another Reply
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div></main></div>);
}