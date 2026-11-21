import { useEffect, useState } from "react";
import { Bot, BookOpen, CircleHelp, Database, RefreshCw, Save, Send, ShieldCheck } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Badge } from "@/components/ui/form";
import { Button } from "@/components/ui/button";
import { Checkbox, FormField, Input, Select, Textarea } from "@/components/ui/form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

type Settings = {
  enabled: boolean; display_name: string; welcome_en: string; welcome_bn: string; default_language: "en" | "bn";
  base_url: string; model: string; embedding_model: string; api_key_masked: string; configured: boolean;
  temperature: string; max_response_tokens: number; context_messages: number; daily_message_limit: number; retention_days: number; provider_state: string; input_cost_per_million: string; output_cost_per_million: string;
};
type Article = { id: string; title_en: string; title_bn: string; body_en: string; body_bn: string; is_published: boolean; source_type: string; source_url: string };
type Source = { id: string; title: string; language: string; version: string; status: string; indexed_at: string | null; error_code: string; chunks: number; is_enabled: boolean };
type Analytics = { conversations: number; messages_today: number; messages_this_month: number; user_messages_today: number; responses_today: number; failed_today: number; bengali_conversations: number; english_conversations: number; prompt_tokens_today: number; completion_tokens_today: number; estimated_cost_usd_today: string | null; cost_estimate_configured: boolean; feedback_helpful: number; feedback_not_helpful: number; recent?: { id: string; language: string; message_count: number; updated_at: string; source_count: number }[] };
type SuggestedQuestion = { id: string; question_en: string; question_bn: string; display_order: number; is_active: boolean };

const emptyArticle = { title_en: "", title_bn: "", body_en: "", body_bn: "", is_published: false };

export function AdminAssistantPage() {
  const qc = useQueryClient();
  const settingsQuery = useQuery({ queryKey: ["admin", "assistant", "settings"], queryFn: () => api<Settings>("/admin/assistant/settings/") });
  const articlesQuery = useQuery({ queryKey: ["admin", "assistant", "articles"], queryFn: () => api<Article[]>("/admin/assistant/articles/") });
  const sourcesQuery = useQuery({ queryKey: ["admin", "assistant", "sources"], queryFn: () => api<Source[]>("/admin/assistant/sources/") });
  const analyticsQuery = useQuery({ queryKey: ["admin", "assistant", "analytics"], queryFn: () => api<Analytics>("/admin/assistant/analytics/") });
  const questionsQuery = useQuery({ queryKey: ["admin", "assistant", "questions"], queryFn: () => api<SuggestedQuestion[]>("/admin/assistant/questions/") });
  const [settings, setSettings] = useState<Settings | null>(null);
  const [key, setKey] = useState("");
  const [article, setArticle] = useState(emptyArticle);
  const [articleId, setArticleId] = useState<string | null>(null);
  const [question, setQuestion] = useState({ question_en: "", question_bn: "", display_order: 0, is_active: true });
  const [questionId, setQuestionId] = useState<string | null>(null);
  const [importTitle, setImportTitle] = useState("");
  const [importUrl, setImportUrl] = useState("");
  const [importFile, setImportFile] = useState<File | null>(null);
  useEffect(() => { if (settingsQuery.data) setSettings(settingsQuery.data); }, [settingsQuery.data]);

  const saveSettings = useMutation({
    mutationFn: () => api<Settings>("/admin/assistant/settings/", { method: "PUT", json: { ...settings, api_key: key } }),
    onSuccess: (data) => { setSettings(data); setKey(""); qc.invalidateQueries({ queryKey: ["admin", "assistant"] }); toast.success("AI Assistant settings saved."); },
    onError: (e: Error) => toast.error(e.message),
  });
  const clearCredential = useMutation({
    mutationFn: () => api<Settings>("/admin/assistant/settings/", { method: "PUT", json: { ...settings, api_key: "", clear_api_key: true } }),
    onSuccess: (data) => { setSettings(data); qc.invalidateQueries({ queryKey: ["admin", "assistant"] }); toast.success("Provider credential removed. Assistant replies are now unavailable."); },
    onError: (e: Error) => toast.error(e.message),
  });
  const testProvider = useMutation({
    mutationFn: () => api<{ ok: boolean }>("/admin/assistant/test/", { method: "POST", json: {} }),
    onSuccess: () => { toast.success("AI provider connection succeeded."); qc.invalidateQueries({ queryKey: ["admin", "assistant", "settings"] }); },
    onError: (e: Error) => toast.error(`Provider test failed: ${e.message}`),
  });
  const saveArticle = useMutation({
    mutationFn: () => api<Article>(articleId ? `/admin/assistant/articles/${articleId}/` : "/admin/assistant/articles/", { method: "POST", json: article }),
    onSuccess: () => { setArticle(emptyArticle); setArticleId(null); qc.invalidateQueries({ queryKey: ["admin", "assistant", "articles"] }); toast.success("Knowledge article saved."); },
    onError: (e: Error) => toast.error(e.message),
  });
  const deleteArticle = useMutation({ mutationFn: (id: string) => api(`/admin/assistant/articles/${id}/`, { method: "DELETE" }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin", "assistant", "articles"] }); toast.success("Article deleted."); } });
  const importSource = useMutation({
    mutationFn: () => {
      if (importFile) {
        const form = new FormData();
        form.set("title_en", importTitle);
        form.set("file", importFile);
        return api<Article>("/admin/assistant/import/", { method: "POST", body: form });
      }
      return api<Article>("/admin/assistant/import/", { method: "POST", json: { title_en: importTitle, source_url: importUrl } });
    },
    onSuccess: () => { setImportTitle(""); setImportUrl(""); setImportFile(null); qc.invalidateQueries({ queryKey: ["admin", "assistant", "articles"] }); toast.success("Imported as an unpublished draft. Review before publishing."); },
    onError: (e: Error) => toast.error(e.message),
  });
  const reindex = useMutation({ mutationFn: () => api<{ queued: boolean }>("/admin/assistant/reindex/", { method: "POST", json: {} }), onSuccess: (data) => { toast.success(data.queued ? "Knowledge re-index queued." : "Knowledge re-index is pending the background tick."); qc.invalidateQueries({ queryKey: ["admin", "assistant", "sources"] }); } });
  const saveQuestion = useMutation({
    mutationFn: () => api<SuggestedQuestion>(questionId ? `/admin/assistant/questions/${questionId}/` : "/admin/assistant/questions/", { method: "POST", json: question }),
    onSuccess: () => { setQuestion({ question_en: "", question_bn: "", display_order: 0, is_active: true }); setQuestionId(null); qc.invalidateQueries({ queryKey: ["admin", "assistant", "questions"] }); toast.success("Suggested question saved."); },
    onError: (e: Error) => toast.error(e.message),
  });
  const deleteQuestion = useMutation({ mutationFn: (id: string) => api(`/admin/assistant/questions/${id}/`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "assistant", "questions"] }) });
  const toggleSource = useMutation({ mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => api(`/admin/assistant/sources/${id}/`, { method: "PATCH", json: { is_enabled: enabled } }), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "assistant", "sources"] }) });
  if (!settings && settingsQuery.isLoading) return <p role="status">Loading AI assistant settings…</p>;
  if (!settings) return <p role="alert">Could not load AI assistant settings.</p>;

  const counts = analyticsQuery.data;
  return <div className="space-y-6">
    <PageHeader title="AI Assistant" description="Configure the public informational assistant and manage its approved knowledge." />
    <aside className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
      <p className="flex items-center gap-2 font-semibold"><ShieldCheck className="size-4" /> Safe, read-only support</p>
      <p className="mt-1">The assistant must not approve bookings, verify payments, modify subscriptions, or perform account actions. Answers can be incomplete; visitors should verify important details with support.</p>
    </aside>

    {counts && <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {[ ["Conversations", counts.conversations], ["Messages today", counts.messages_today], ["Messages this month", counts.messages_this_month], ["Responses today", counts.responses_today], ["Failed today", counts.failed_today], ["Bengali conversations", counts.bengali_conversations], ["English conversations", counts.english_conversations] ].map(([label, value]) => <Card key={label}><CardContent className="p-4"><p className="text-sm text-muted-foreground">{label}</p><p className="mt-1 text-2xl font-bold">{value}</p></CardContent></Card>)}
    </div>}

    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><Bot className="size-5" /> Provider and behavior</CardTitle></CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        <Checkbox label="Enable assistant on the public homepage" checked={settings.enabled} onChange={(e) => setSettings({ ...settings, enabled: e.target.checked })} />
        <FormField label="Assistant display name">{(id) => <Input id={id} value={settings.display_name} onChange={(e) => setSettings({ ...settings, display_name: e.target.value })} />}</FormField>
        <FormField label="Default response language">{(id) => <Select id={id} value={settings.default_language} onChange={(e) => setSettings({ ...settings, default_language: e.target.value as "en" | "bn" })}><option value="en">English</option><option value="bn">বাংলা</option></Select>}</FormField>
        <FormField label="OpenAI-compatible API base URL" hint="Must use HTTPS. The credential stays encrypted on the server.">{(id) => <Input id={id} type="url" value={settings.base_url} onChange={(e) => setSettings({ ...settings, base_url: e.target.value })} />}</FormField>
        <FormField label="Chat model">{(id) => <Input id={id} value={settings.model} onChange={(e) => setSettings({ ...settings, model: e.target.value })} />}</FormField>
        <FormField label="Embedding model">{(id) => <Input id={id} value={settings.embedding_model} onChange={(e) => setSettings({ ...settings, embedding_model: e.target.value })} />}</FormField>
        <FormField label="API credential" hint={settings.configured ? `Saved: ${settings.api_key_masked}. Leave blank to keep it.` : "Add the provider key to enable real AI responses."}>{(id) => <Input id={id} type="password" autoComplete="new-password" value={key} onChange={(e) => setKey(e.target.value)} placeholder={settings.configured ? settings.api_key_masked : "Provider API key"} />}</FormField>
        <FormField label="Daily message cap">{(id) => <Input id={id} type="number" min={1} max={100000} value={settings.daily_message_limit} onChange={(e) => setSettings({ ...settings, daily_message_limit: Number(e.target.value) })} />}</FormField>
        <FormField label="Conversation retention (days)">{(id) => <Input id={id} type="number" min={1} max={365} value={settings.retention_days} onChange={(e) => setSettings({ ...settings, retention_days: Number(e.target.value) })} />}</FormField>
        <FormField label="Input cost per 1M tokens (USD)" hint="Optional model price for estimated usage cost.">{(id) => <Input id={id} type="number" min={0} step="0.000001" value={settings.input_cost_per_million} onChange={(e) => setSettings({ ...settings, input_cost_per_million: e.target.value })} />}</FormField>
        <FormField label="Output cost per 1M tokens (USD)" hint="Optional model price for estimated usage cost.">{(id) => <Input id={id} type="number" min={0} step="0.000001" value={settings.output_cost_per_million} onChange={(e) => setSettings({ ...settings, output_cost_per_million: e.target.value })} />}</FormField>
        <FormField label="Maximum response tokens">{(id) => <Input id={id} type="number" min={100} max={2000} value={settings.max_response_tokens} onChange={(e) => setSettings({ ...settings, max_response_tokens: Number(e.target.value) })} />}</FormField>
        <FormField label="Context messages">{(id) => <Input id={id} type="number" min={2} max={20} value={settings.context_messages} onChange={(e) => setSettings({ ...settings, context_messages: Number(e.target.value) })} />}</FormField>
        <FormField label="Temperature (0–1)">{(id) => <Input id={id} type="number" min={0} max={1} step="0.05" value={settings.temperature} onChange={(e) => setSettings({ ...settings, temperature: e.target.value })} />}</FormField>
        <FormField label="English welcome message">{(id) => <Textarea id={id} rows={3} value={settings.welcome_en} onChange={(e) => setSettings({ ...settings, welcome_en: e.target.value })} />}</FormField>
        <FormField label="Bengali welcome message">{(id) => <Textarea id={id} rows={3} value={settings.welcome_bn} onChange={(e) => setSettings({ ...settings, welcome_bn: e.target.value })} />}</FormField>
        <div className="flex flex-wrap items-center gap-2 md:col-span-2">
          <Button onClick={() => saveSettings.mutate()} disabled={saveSettings.isPending}><Save className="size-4" /> Save settings</Button>
          {settings.configured && <Button variant="outline" onClick={() => { if (window.confirm("Remove the saved AI provider credential?")) clearCredential.mutate(); }} disabled={clearCredential.isPending}>Remove credential</Button>}
          <Button variant="outline" onClick={() => testProvider.mutate()} disabled={!settings.configured || testProvider.isPending}><Send className="size-4" /> Test provider</Button>
          <Badge tone={settings.provider_state === "healthy" ? "green" : settings.provider_state === "unavailable" ? "red" : "amber"}>Provider: {settings.provider_state}</Badge>
          <span className="text-xs text-muted-foreground">Test makes a small billable request to the configured provider.</span>
        </div>
      </CardContent>
    </Card>

    <div className="grid gap-6 xl:grid-cols-2">
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><BookOpen className="size-5" /> Approved knowledge articles</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">Only published articles are indexed. Content is treated as reference data, never as instructions.</p>
          <div className="space-y-3 rounded-lg border bg-muted/20 p-3">
            <p className="text-sm font-semibold">Import a reviewed source</p>
            <FormField label="English title">{(id) => <Input id={id} value={importTitle} onChange={(e) => setImportTitle(e.target.value)} />}</FormField>
            <FormField label="Public page URL" hint="Only HTTPS pages on the configured public-site host are allowed; redirects and private hosts are blocked.">{(id) => <Input id={id} type="url" value={importUrl} onChange={(e) => { setImportUrl(e.target.value); if (e.target.value) setImportFile(null); }} />}</FormField>
            <FormField label="Or upload UTF-8 text/Markdown (.txt, .md, max 1 MB)">{(id) => <Input id={id} type="file" accept=".txt,.md,.markdown,text/plain,text/markdown" onChange={(e) => { setImportFile(e.target.files?.[0] ?? null); if (e.target.files?.length) setImportUrl(""); }} />}</FormField>
            <Button variant="outline" onClick={() => importSource.mutate()} disabled={!importTitle.trim() || (!importUrl.trim() && !importFile) || importSource.isPending}><BookOpen className="size-4" /> Import as draft</Button>
          </div>
          <FormField label="English title">{(id) => <Input id={id} value={article.title_en} onChange={(e) => setArticle({ ...article, title_en: e.target.value })} />}</FormField>
          <FormField label="Bengali title">{(id) => <Input id={id} value={article.title_bn} onChange={(e) => setArticle({ ...article, title_bn: e.target.value })} />}</FormField>
          <FormField label="English content">{(id) => <Textarea id={id} rows={4} value={article.body_en} onChange={(e) => setArticle({ ...article, body_en: e.target.value })} />}</FormField>
          <FormField label="Bengali content">{(id) => <Textarea id={id} rows={4} value={article.body_bn} onChange={(e) => setArticle({ ...article, body_bn: e.target.value })} />}</FormField>
          <Checkbox label="Published and available to the public assistant" checked={article.is_published} onChange={(e) => setArticle({ ...article, is_published: e.target.checked })} />
          <div className="flex gap-2"><Button onClick={() => saveArticle.mutate()} disabled={saveArticle.isPending || !article.title_en || !article.body_en}><Save className="size-4" /> {articleId ? "Update article" : "Save article"}</Button>{articleId && <Button variant="outline" onClick={() => { setArticle(emptyArticle); setArticleId(null); }}>Cancel edit</Button>}</div>
          <div className="divide-y rounded-lg border">{articlesQuery.data?.map((item) => <div key={item.id} className="flex items-center gap-2 p-3"><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{item.title_en}</p><p className="text-xs text-muted-foreground">{item.is_published ? "Published" : "Draft"} · {item.source_type}{item.source_url ? ` · ${item.source_url}` : ""}</p></div><Button size="sm" variant="outline" onClick={() => { setArticleId(item.id); setArticle({ title_en: item.title_en, title_bn: item.title_bn, body_en: item.body_en, body_bn: item.body_bn, is_published: item.is_published }); }}>Edit</Button><Button size="sm" variant="ghost" onClick={() => { if (window.confirm("Delete this knowledge article?")) deleteArticle.mutate(item.id); }}>Delete</Button></div>)}</div>
        </CardContent>
      </Card>

      <div className="space-y-6">
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><Database className="size-5" /> Knowledge indexing</CardTitle></CardHeader><CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">Indexes published FAQs, active plans, current SMS pricing, published legal versions, and published help articles. Draft legal and help content is excluded.</p>
          <Button variant="outline" onClick={() => reindex.mutate()} disabled={reindex.isPending}><RefreshCw className={`size-4 ${reindex.isPending ? "animate-spin" : ""}`} /> Re-index public knowledge</Button>
          <div className="max-h-80 divide-y overflow-y-auto rounded-lg border">{sourcesQuery.data?.length ? sourcesQuery.data.map((source) => <div key={source.id} className="flex items-center gap-2 p-3"><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{source.title}</p><p className="text-xs text-muted-foreground">{source.language.toUpperCase()} · {source.chunks} chunks · {source.indexed_at ? new Date(source.indexed_at).toLocaleString() : "Not indexed"}</p>{source.error_code && <p className="text-xs text-destructive">{source.error_code}</p>}</div><Badge tone={source.status === "indexed" ? "green" : source.status === "failed" ? "red" : "amber"}>{source.status}</Badge><Button size="sm" variant="outline" onClick={() => toggleSource.mutate({ id: source.id, enabled: !source.is_enabled })}>{source.is_enabled ? "Disable" : "Enable"}</Button></div>) : <p className="p-4 text-sm text-muted-foreground">No knowledge sources indexed yet.</p>}</div>
        </CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><CircleHelp className="size-5" /> Suggested questions</CardTitle></CardHeader><CardContent className="space-y-3">
          <FormField label="English question">{(id) => <Input id={id} value={question.question_en} onChange={(e) => setQuestion({ ...question, question_en: e.target.value })} />}</FormField>
          <FormField label="Bengali question">{(id) => <Input id={id} value={question.question_bn} onChange={(e) => setQuestion({ ...question, question_bn: e.target.value })} />}</FormField>
          <div className="flex items-center gap-3"><FormField label="Display order">{(id) => <Input id={id} type="number" value={question.display_order} onChange={(e) => setQuestion({ ...question, display_order: Number(e.target.value) })} />}</FormField><Checkbox label="Active" checked={question.is_active} onChange={(e) => setQuestion({ ...question, is_active: e.target.checked })} /></div>
          <div className="flex gap-2"><Button onClick={() => saveQuestion.mutate()} disabled={!question.question_en || saveQuestion.isPending}><Save className="size-4" /> {questionId ? "Update question" : "Add question"}</Button>{questionId && <Button variant="outline" onClick={() => { setQuestionId(null); setQuestion({ question_en: "", question_bn: "", display_order: 0, is_active: true }); }}>Cancel</Button>}</div>
          <div className="divide-y rounded-lg border">{questionsQuery.data?.map((item) => <div key={item.id} className="flex items-center gap-2 p-3"><div className="min-w-0 flex-1"><p className="text-sm">{item.question_en}</p><p className="text-xs text-muted-foreground">{item.question_bn || "No Bengali text"} · {item.is_active ? "Active" : "Inactive"}</p></div><Button size="sm" variant="outline" onClick={() => { setQuestionId(item.id); setQuestion({ question_en: item.question_en, question_bn: item.question_bn, display_order: item.display_order, is_active: item.is_active }); }}>Edit</Button><Button size="sm" variant="ghost" onClick={() => deleteQuestion.mutate(item.id)}>Delete</Button></div>)}</div>
        </CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><CircleHelp className="size-5" /> Usage and feedback</CardTitle></CardHeader><CardContent className="grid grid-cols-2 gap-3 text-sm">
          <p>Visitor questions today <strong className="block text-lg">{counts?.user_messages_today ?? 0}</strong></p><p>Provider tokens today <strong className="block text-lg">{(counts?.prompt_tokens_today ?? 0) + (counts?.completion_tokens_today ?? 0)}</strong></p><p>Helpful <strong className="block text-lg">{counts?.feedback_helpful ?? 0}</strong></p><p>Not helpful <strong className="block text-lg">{counts?.feedback_not_helpful ?? 0}</strong></p>
          <p className="col-span-2 text-xs text-muted-foreground">Provider tokens are shown when reported. Estimated chat-completion cost today: {counts?.estimated_cost_usd_today ? `USD $${counts.estimated_cost_usd_today}` : counts?.cost_estimate_configured ? "Unavailable (provider did not return token usage)." : "Not configured; enter the model's input/output price per million tokens above."} This estimate excludes embedding/indexing costs. Conversation text is not displayed in this dashboard.</p>
          <div className="col-span-2 space-y-2"><p className="font-medium">Recent conversation metadata</p>{counts?.recent?.slice(0, 20).map((row) => <div key={row.id} className="flex flex-wrap justify-between gap-2 border-t pt-2 text-xs text-muted-foreground"><span>{row.id.slice(0, 8)} · {row.language.toUpperCase()} · {row.message_count} messages · {row.source_count} source references</span><time>{new Date(row.updated_at).toLocaleString()}</time></div>)}</div>
        </CardContent></Card>
      </div>
    </div>
  </div>;
}
