import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, Checkbox, ErrorState, FormField, Input, Select } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { ClientLogoShowcase } from "@/features/public/ClientLogoShowcase";
import { errorText } from "@/features/workspace/hooks";
import { api } from "@/lib/api";

interface ClientItem { id: string; slug: string; name: string; logo_url: string | null; mode: "auto" | "include" | "hide"; display_order: number; eligible: boolean }
interface PlanOption { id: string; name: string; period: string; months: number }
interface ShowcaseConfig {
  enabled: boolean;
  auto_include: boolean;
  eligible_plan_ids: string[];
  heading_en: string;
  heading_bn: string;
  subtitle_en: string;
  subtitle_bn: string;
  plans: PlanOption[];
  clients: ClientItem[];
}
type ShowcaseDraft = Pick<ShowcaseConfig, "enabled" | "auto_include" | "eligible_plan_ids" | "heading_en" | "heading_bn" | "subtitle_en" | "subtitle_bn">;

export function AdminClientShowcasePage() {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<ShowcaseDraft | null>(null);
  const query = useQuery({ queryKey: ["admin", "client-showcase"], queryFn: () => api<ShowcaseConfig>("/admin/homepage/client-showcase/") });
  const current = query.data ? { ...query.data, ...draft } : undefined;
  const save = useMutation({
    mutationFn: () => {
      const values = draft ?? query.data!;
      const { enabled, auto_include, eligible_plan_ids, heading_en, heading_bn, subtitle_en, subtitle_bn } = values;
      return api<ShowcaseConfig>("/admin/homepage/client-showcase/", { method: "PATCH", json: { enabled, auto_include, eligible_plan_ids, heading_en, heading_bn, subtitle_en, subtitle_bn } });
    },
    onSuccess: (data) => { setDraft(null); qc.setQueryData(["admin", "client-showcase"], data); toast.success("Client showcase settings saved"); },
    onError: (error) => toast.error(errorText(error)),
  });
  const updateItem = useMutation({
    mutationFn: ({ id, mode, display_order }: { id: string; mode: ClientItem["mode"]; display_order: number }) =>
      api(`/admin/homepage/client-showcase/${id}/`, { method: "PATCH", json: { mode, display_order } }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["admin", "client-showcase"] }); void qc.invalidateQueries({ queryKey: ["public", "client-showcase"] }); toast.success("Showcase entry updated"); },
    onError: (error) => toast.error(errorText(error)),
  });
  const edit = (changes: Partial<ShowcaseDraft>) => setDraft({
    enabled: current?.enabled ?? true,
    auto_include: current?.auto_include ?? true,
    eligible_plan_ids: current?.eligible_plan_ids ?? [],
    heading_en: current?.heading_en ?? "Our Trusted Clients",
    heading_bn: current?.heading_bn ?? "আমাদের সম্মানিত গ্রাহক",
    subtitle_en: current?.subtitle_en ?? "Turf businesses growing with TURFBARI.",
    subtitle_bn: current?.subtitle_bn ?? "যেসব টার্ফ ব্যবসা TURFBARI-এর সঙ্গে এগিয়ে যাচ্ছে।",
    ...changes,
  });

  return <>
    <PageHeader title="Client Showcase" description="Show real active turf businesses with a current approved subscription and an uploaded profile logo." />
    {query.isPending ? <Skeleton className="h-56" /> : query.isError || !current ? <ErrorState error={query.error ?? new Error("Client showcase settings are unavailable.")} onRetry={() => void query.refetch()} /> : <>
      <Card>
        <CardHeader><CardTitle>Homepage showcase settings</CardTitle></CardHeader>
        <CardContent>
          <form className="grid gap-4 md:grid-cols-2" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
            <div className="space-y-3 md:col-span-2">
              <Checkbox label="Enable the homepage client showcase" checked={current.enabled} onChange={(event) => edit({ enabled: event.target.checked })} />
              <Checkbox label="Automatically include eligible active clients" checked={current.auto_include} onChange={(event) => edit({ auto_include: event.target.checked })} />
            </div>
            <FormField label="Heading (English)">{(id) => <Input id={id} maxLength={120} value={current.heading_en} onChange={(event) => edit({ heading_en: event.target.value })} />}</FormField>
            <FormField label="Heading (Bengali)">{(id) => <Input id={id} maxLength={120} value={current.heading_bn} onChange={(event) => edit({ heading_bn: event.target.value })} />}</FormField>
            <FormField label="Subtitle (English)">{(id) => <Input id={id} maxLength={200} value={current.subtitle_en} onChange={(event) => edit({ subtitle_en: event.target.value })} />}</FormField>
            <FormField label="Subtitle (Bengali)">{(id) => <Input id={id} maxLength={200} value={current.subtitle_bn} onChange={(event) => edit({ subtitle_bn: event.target.value })} />}</FormField>
            <fieldset className="space-y-2 md:col-span-2">
              <legend className="mb-2 text-sm font-medium">Eligible plans <span className="font-normal text-muted-foreground">(none selected means every plan)</span></legend>
              <div className="flex flex-wrap gap-x-5 gap-y-2">{current.plans.map((plan) => <Checkbox key={plan.id} label={plan.name} checked={current.eligible_plan_ids.includes(plan.id)} onChange={(event) => edit({ eligible_plan_ids: event.target.checked ? [...current.eligible_plan_ids, plan.id] : current.eligible_plan_ids.filter((id) => id !== plan.id) })} />)}</div>
            </fieldset>
            <Button type="submit" disabled={save.isPending} className="md:col-span-2 md:justify-self-end"><Save /> Save settings</Button>
          </form>
        </CardContent>
      </Card>

      <Card className="mt-5">
        <CardHeader><CardTitle>Eligible client accounts</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {!current.clients.length ? <p className="text-sm text-muted-foreground">No accounts currently have an active subscription. Eligible clients will appear here automatically.</p> : current.clients.map((client) => <ClientRow key={client.id} client={client} pending={updateItem.isPending} onSave={(mode, display_order) => updateItem.mutate({ id: client.id, mode, display_order })} />)}
        </CardContent>
      </Card>

      <Card className="mt-5 overflow-hidden">
        <CardHeader><CardTitle className="flex items-center gap-2"><Eye className="size-4" /> Preview</CardTitle></CardHeader>
        <CardContent className="p-0">
          {current.enabled ? <ClientLogoShowcase
            clients={current.clients.filter((client) => client.eligible && client.mode !== "hide" && (current.auto_include || client.mode === "include"))
              .sort((a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name))
              .filter((client): client is ClientItem & { logo_url: string } => Boolean(client.logo_url))}
            heading={current.heading_en}
            subtitle={current.subtitle_en}
          /> : <p className="p-6 text-sm text-muted-foreground">The showcase is disabled.</p>}
        </CardContent>
      </Card>
    </>}
  </>;
}

function ClientRow({ client, pending, onSave }: { client: ClientItem; pending: boolean; onSave: (mode: ClientItem["mode"], order: number) => void }) {
  const [mode, setMode] = useState(client.mode);
  const [order, setOrder] = useState(client.display_order);
  useEffect(() => { setMode(client.mode); setOrder(client.display_order); }, [client.mode, client.display_order]);
  return <div className="grid items-center gap-3 rounded-xl border p-3 sm:grid-cols-[4rem_minmax(0,1fr)_10rem_7rem_auto]">
    <div className="flex size-14 items-center justify-center rounded-lg border bg-muted p-2">{client.logo_url ? <img src={client.logo_url} alt="" className="max-h-full max-w-full object-contain" /> : <span className="text-xs text-muted-foreground">No logo</span>}</div>
    <div className="min-w-0"><p className="truncate font-semibold">{client.name}</p><p className="text-xs text-muted-foreground">/{client.slug}</p></div>
    <div className="flex items-center gap-2"><Select aria-label={`Showcase visibility for ${client.name}`} value={mode} onChange={(event) => setMode(event.target.value as ClientItem["mode"])}><option value="auto">Automatic</option><option value="include">Include</option><option value="hide">Hide</option></Select><Badge tone={client.eligible ? "green" : "amber"}>{client.eligible ? "Eligible" : "Needs logo"}</Badge></div>
    <Input aria-label={`Display order for ${client.name}`} type="number" min={0} max={65535} value={order} onChange={(event) => setOrder(Number(event.target.value))} />
    <Button size="sm" variant="outline" disabled={pending} onClick={() => onSave(mode, order)}>Save</Button>
  </div>;
}
