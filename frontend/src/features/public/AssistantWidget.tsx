import { Bot, LoaderCircle, MessageCircle, Minus, Plus, RotateCcw, Send, ThumbsDown, ThumbsUp, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { FormattedText } from "@/components/content/FormattedText";

type Status = {
  enabled: boolean; available: boolean; display_name: string;
  welcome: { en: string; bn: string }; service_state: "ready" | "disabled"; service_mode: "local_knowledge";
  suggested_questions: { en: string; bn: string }[]; privacy_note: string;
};
type Citation = { title: string; url: string; version: string; language: string };
type ChatItem = { id: string; role: "user" | "assistant"; content: string; links?: { label: string; url: string }[]; sources?: Citation[] };
type Session = { conversation_id: string; conversation_token: string; messages: ChatItem[] };
const SESSION_KEY = "turfbari_assistant_session_v1";

function loadSession(): Session | null {
  try { const value = sessionStorage.getItem(SESSION_KEY); return value ? JSON.parse(value) as Session : null; } catch { return null; }
}

export function AssistantWidget() {
  const { language, t } = useLanguage();
  const [status, setStatus] = useState<Status | null>(null);
  const [open, setOpen] = useState(false);
  const [session, setSession] = useState<Session | null>(loadSession);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [failedMessageId, setFailedMessageId] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    void api<Status>("/public/assistant/status/").then((data) => active && setStatus(data)).catch(() => active && setStatus(null));
    return () => { active = false; };
  }, []);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [session?.messages.length, busy, open]);
  useEffect(() => {
    if (!session) { sessionStorage.removeItem(SESSION_KEY); return; }
    try { sessionStorage.setItem(SESSION_KEY, JSON.stringify(session)); } catch { /* conversation remains active in memory */ }
  }, [session]);

  async function newConversation() {
    setError("");
    try {
      const created = await api<{ conversation_id: string; conversation_token: string }>("/public/assistant/conversations/", { method: "POST", json: { language } });
      setSession({ ...created, messages: [] });
    } catch { setError(t("Could not start a conversation. Please retry.")); }
  }

  async function sendMessage(text = input, requestedId?: string) {
    const message = text.trim();
    if (!message || busy || message.length > 2000) return;
    setBusy(true); setError(""); setInput("");
    const clientMessageId = requestedId ?? crypto.randomUUID();
    try {
      let active: Session;
      if (session) active = session;
      else {
        const created = await api<{ conversation_id: string; conversation_token: string }>("/public/assistant/conversations/", { method: "POST", json: { language } });
        active = { ...created, messages: [] };
      }
      const userItem: ChatItem = { id: clientMessageId, role: "user", content: message };
      if (!requestedId) setSession({ ...active, messages: [...active.messages, userItem] });
      const result = await api<{ message: { id: number; content: string }; links: ChatItem["links"]; sources: Citation[] }>("/public/assistant/messages/", {
        method: "POST", json: { ...active, message, language, client_message_id: clientMessageId },
      });
      setSession((current) => current ? { ...current, messages: [...current.messages, { id: String(result.message.id), role: "assistant", content: result.message.content, links: result.links, sources: result.sources }] } : current);
      setFailedMessageId(null);
    } catch (cause) {
      setInput(message);
      setFailedMessageId(clientMessageId);
      setError(cause instanceof Error ? cause.message : t("The assistant is temporarily unavailable. Please retry."));
    } finally { setBusy(false); }
  }

  async function clearConversation() {
    if (session) {
      try { await api("/public/assistant/conversations/clear/", { method: "POST", json: session }); } catch { /* clear locally even if the service is unavailable */ }
    }
    setSession(null); setError("");
    await newConversation();
  }

  async function feedback(messageId: string, helpful: boolean) {
    if (!session || !/^\d+$/.test(messageId)) return;
    await api("/public/assistant/feedback/", { method: "POST", json: { ...session, message_id: Number(messageId), helpful } }).catch(() => undefined);
  }

  if (!status?.enabled) return null;
  const welcome = language === "bn" ? status.welcome.bn || t(status.welcome.en) : status.welcome.en;
  const ready = status.available && status.service_state === "ready";
  const stateLabel = ready ? t("TURFBARI knowledge ready") : t("Assistant disabled");
  const btnLabel = t("Ask TURFBARI Assistant");

  return <div className="fixed bottom-[max(1rem,env(safe-area-inset-bottom))] right-4 z-50 sm:right-6">
    {open ? <section aria-label={status.display_name} className="mb-3 flex h-[min(680px,calc(100dvh-7rem))] w-[min(25rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border bg-background shadow-2xl">
      <header className="flex items-center gap-3 border-b bg-primary px-4 py-3 text-primary-foreground">
        <span className="grid size-10 place-items-center rounded-full bg-white/15"><Bot className="size-5" /></span>
        <div className="min-w-0 flex-1"><p className="truncate font-semibold">{status.display_name}</p><p className="flex items-center gap-1.5 text-xs opacity-90"><span className={`size-2 rounded-full ${ready ? "bg-lime-300" : "bg-amber-300"}`} />{stateLabel}</p></div>
        <button type="button" onClick={() => void newConversation()} className="rounded p-2 hover:bg-white/10" aria-label={t("New conversation")} title={t("New conversation")}><RotateCcw className="size-4" /></button>
        <button type="button" onClick={() => void clearConversation()} className="rounded p-2 hover:bg-white/10" aria-label={t("Clear conversation")} title={t("Clear conversation")}><Trash2 className="size-4" /></button>
        <button type="button" onClick={() => setOpen(false)} className="rounded p-2 hover:bg-white/10" aria-label={t("Minimize assistant")}><Minus className="size-4" /></button>
        <button type="button" onClick={() => setOpen(false)} className="rounded p-2 hover:bg-white/10" aria-label={t("Close assistant")}><X className="size-4" /></button>
      </header>
      <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite" aria-relevant="additions text">
        {!session?.messages.length && <div className="max-w-[92%] rounded-xl rounded-tl-sm bg-muted p-3 text-sm leading-relaxed">{welcome}<p className="mt-3 text-xs text-muted-foreground">{t("Do not send passwords, payment transaction details, or private customer information.")}</p></div>}
        {session?.messages.map((item) => <div key={item.id} className={`max-w-[92%] rounded-xl p-3 text-sm leading-relaxed ${item.role === "user" ? "ml-auto rounded-tr-sm bg-primary text-primary-foreground" : "rounded-tl-sm bg-muted"}`}>
            {item.role === "assistant" ? <><FormattedText text={item.content} />{item.links?.length ? <div className="mt-2 flex flex-wrap gap-2">{item.links.map((link) => <Link key={link.url} to={link.url} onClick={() => setOpen(false)} className="text-primary underline underline-offset-2">{link.label}</Link>)}</div> : null}{item.sources?.length ? <div className="mt-3 border-t pt-2 text-xs"><p className="mb-1 font-medium text-muted-foreground">{t("Sources")}</p><ul className="space-y-1">{item.sources.map((source) => <li key={`${source.title}-${source.version}-${source.language}`}><Link to={source.url} onClick={() => setOpen(false)} className="text-primary underline underline-offset-2">{source.title}</Link><span className="ml-1 text-muted-foreground">· {source.language.toUpperCase()} · {source.version}</span></li>)}</ul></div> : null}
            {/^-?\d+$/.test(item.id) && <div className="mt-2 flex gap-2 border-t pt-2"><button onClick={() => void feedback(item.id, true)} className="rounded p-1 text-muted-foreground hover:text-primary" aria-label={t("Helpful")}><ThumbsUp className="size-3.5" /></button><button onClick={() => void feedback(item.id, false)} className="rounded p-1 text-muted-foreground hover:text-primary" aria-label={t("Not helpful")}><ThumbsDown className="size-3.5" /></button></div>}</> : item.content}
        </div>)}
        {busy && <div role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" />{t("Thinking")}</div>}
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}<button type="button" onClick={() => void sendMessage(input, failedMessageId ?? undefined)} className="ml-2 underline">{t("Retry")}</button></div>}
        {!session?.messages.length && status.suggested_questions.length > 0 && <div className="flex flex-wrap gap-2">{status.suggested_questions.map((q) => { const text = language === "bn" && q.bn ? q.bn : q.en; return <button key={q.en} type="button" disabled={!ready} onClick={() => void sendMessage(text)} className="rounded-full border px-3 py-1.5 text-left text-xs hover:border-primary disabled:opacity-50">{text}</button>; })}</div>}
        <div ref={bottom} />
      </div>
      <form className="flex items-end gap-2 border-t p-3" onSubmit={(event) => { event.preventDefault(); void sendMessage(); }}>
        <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(); } }} rows={1} maxLength={2000} disabled={!ready || busy} placeholder={t("Ask about TURFBARI")} aria-label={t("Your message")} className="max-h-28 min-h-10 flex-1 resize-y rounded-lg border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60" />
        <button type="submit" disabled={!ready || busy || !input.trim()} className="grid size-10 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground disabled:opacity-50" aria-label={t("Send message")}><Send className="size-4" /></button>
      </form>
      <p className="px-4 pb-2 text-center text-[10px] text-muted-foreground">{t("AI answers can be incomplete. Verify important details with TURFBARI support.")}</p>
    </section> : null}
    <button type="button" onClick={() => setOpen((value) => !value)} className="ml-auto flex min-h-12 items-center gap-2 rounded-full bg-primary px-4 text-sm font-semibold text-primary-foreground shadow-lg transition hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2" aria-expanded={open} aria-label={open ? t("Close assistant") : btnLabel}>
      {open ? <Plus className="size-5 rotate-45" /> : <MessageCircle className="size-5" />}{!open && <span>{btnLabel}</span>}
    </button>
  </div>;
}
