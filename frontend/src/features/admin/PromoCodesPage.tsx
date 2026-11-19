import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge, type BadgeTone, Checkbox, Dialog, EmptyState, ErrorState, FormField, Input, Table } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText } from "@/features/workspace/hooks";
import { fmtPlainDate } from "@/features/workspace/SubscriptionBanner";
import { ApiError, api } from "@/lib/api";
import type { PromoCode } from "@/lib/types";

type PromoForm = {
  code: string;
  percent_off: string;
  description: string;
  is_active: boolean;
  valid_from: string;
  valid_until: string;
  max_uses: string;
};

const EMPTY_PROMO: PromoForm = {
  code: "",
  percent_off: "10",
  description: "",
  is_active: true,
  valid_from: "",
  valid_until: "",
  max_uses: "",
};

function promoStatus(p: PromoCode): { label: string; tone: BadgeTone } {
  if (!p.is_active) return { label: "Off", tone: "neutral" };
  if (p.is_running) return { label: "Live", tone: "green" };
  const today = new Date().toISOString().slice(0, 10);
  if (p.valid_from && p.valid_from > today) return { label: "Scheduled", tone: "blue" };
  if (p.valid_until && p.valid_until < today) return { label: "Expired", tone: "red" };
  return { label: "Used up", tone: "amber" };
}

function validText(p: PromoCode): string {
  if (!p.valid_from && !p.valid_until) return "Always";
  return `${p.valid_from ? fmtPlainDate(p.valid_from) : "Now"} – ${p.valid_until ? fmtPlainDate(p.valid_until) : "no end"}`;
}

export function AdminPromoCodesPage() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<PromoCode | "new" | null>(null);
  const codes = useQuery({ queryKey: ["admin", "promo-codes"], queryFn: () => api<PromoCode[]>("/admin/promo-codes/") });
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "promo-codes"] });
  const toggle = useMutation({
    mutationFn: (p: PromoCode) => api(`/admin/promo-codes/${p.id}/`, { method: "PATCH", json: { is_active: !p.is_active } }),
    onSuccess: (_, p) => {
      toast.success(p.is_active ? `${p.code} switched off` : `${p.code} switched on`);
      refresh();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const remove = useMutation({
    mutationFn: (p: PromoCode) => api(`/admin/promo-codes/${p.id}/`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Promo code deleted");
      refresh();
    },
    onError: (e) => toast.error(errorText(e)),
  });

  return (
    <>
      <PageHeader
        title="Promo codes"
        description="Percentage discounts turf owners can apply to an unpaid subscription invoice."
        actions={
          <Button onClick={() => setEditing("new")}>
            <Plus /> New promo code
          </Button>
        }
      />
      <Card>
        <CardContent className="p-2 sm:p-4">
          {codes.isPending && <Skeleton className="h-32" />}
          {codes.isError && <ErrorState error={codes.error} onRetry={() => codes.refetch()} />}
          {codes.data?.length === 0 && (
            <EmptyState title="No promo codes yet">Create a code, e.g. WELCOME20 for 20% off, and share it with turf owners.</EmptyState>
          )}
          {codes.data && codes.data.length > 0 && (
            <Table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th className="text-right">Discount</th>
                  <th>Valid</th>
                  <th className="text-right">Used</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {codes.data.map((p) => {
                  const status = promoStatus(p);
                  return (
                    <tr key={p.id}>
                      <td>
                        <span className="font-mono font-semibold">{p.code}</span>
                        {p.description && <span className="block text-xs text-muted-foreground">{p.description}</span>}
                      </td>
                      <td className="tabular text-right font-semibold">{p.percent_off}%</td>
                      <td className="text-sm">{validText(p)}</td>
                      <td className="tabular text-right">
                        {p.times_used}
                        {p.max_uses !== null && <span className="text-muted-foreground"> / {p.max_uses}</span>}
                      </td>
                      <td>
                        <Badge tone={status.tone}>{status.label}</Badge>
                      </td>
                      <td className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button size="sm" variant="outline" onClick={() => toggle.mutate(p)} disabled={toggle.isPending}>
                            {p.is_active ? "Switch off" : "Switch on"}
                          </Button>
                          <Button size="icon" variant="ghost" aria-label={`Edit ${p.code}`} onClick={() => setEditing(p)}>
                            <Pencil />
                          </Button>
                          {p.times_used === 0 && (
                            <Button
                              size="icon"
                              variant="ghost"
                              aria-label={`Delete ${p.code}`}
                              disabled={remove.isPending}
                              onClick={() => {
                                if (window.confirm(`Delete promo code ${p.code}?`)) remove.mutate(p);
                              }}
                            >
                              <Trash2 />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
          <p className="mt-3 px-2 text-xs text-muted-foreground">
            A use counts while an unpaid invoice holds the code and once it is paid; a cancelled order gives the use back. Each turf can pay with a
            code once. A 100% code activates the plan without payment. Used codes can't be deleted — switch them off instead.
          </p>
        </CardContent>
      </Card>
      {editing !== null && <PromoDialog key={editing === "new" ? "new" : editing.id} promo={editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function PromoDialog({ promo, onClose }: { promo: PromoCode | "new"; onClose: () => void }) {
  const qc = useQueryClient();
  const isNew = promo === "new";
  const [form, setForm] = useState<PromoForm>(
    isNew
      ? EMPTY_PROMO
      : {
          code: promo.code,
          percent_off: String(promo.percent_off),
          description: promo.description,
          is_active: promo.is_active,
          valid_from: promo.valid_from ?? "",
          valid_until: promo.valid_until ?? "",
          max_uses: promo.max_uses === null ? "" : String(promo.max_uses),
        },
  );
  const set = (patch: Partial<PromoForm>) => setForm({ ...form, ...patch });
  const save = useMutation({
    mutationFn: () => {
      const json = {
        code: form.code,
        percent_off: Number(form.percent_off),
        description: form.description,
        is_active: form.is_active,
        valid_from: form.valid_from || null,
        valid_until: form.valid_until || null,
        max_uses: form.max_uses ? Number(form.max_uses) : null,
      };
      return isNew ? api("/admin/promo-codes/", { method: "POST", json }) : api(`/admin/promo-codes/${promo.id}/`, { method: "PATCH", json });
    },
    onSuccess: () => {
      toast.success(isNew ? `Promo code ${form.code} created` : "Promo code saved");
      qc.invalidateQueries({ queryKey: ["admin", "promo-codes"] });
      onClose();
    },
  });
  const fields = save.error instanceof ApiError ? save.error.fields : null;
  const err = (name: string) => fields?.[name];
  const percent = Number(form.percent_off) || 0;

  return (
    <Dialog
      open
      onClose={onClose}
      title={isNew ? "New promo code" : `Edit ${promo.code}`}
      description="Owners type the code on their unpaid subscription invoice to get the discount."
    >
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <FormField label="Code" error={err("code")} hint="Letters, numbers, - or _">
          {(id) => (
            <Input
              id={id}
              required
              maxLength={30}
              placeholder="WELCOME20"
              className="font-mono uppercase"
              value={form.code}
              onChange={(e) => set({ code: e.target.value.toUpperCase().replace(/\s/g, "") })}
            />
          )}
        </FormField>
        <FormField
          label="Discount (%)"
          error={err("percent_off")}
          hint={percent >= 100 ? "100% = the plan is free" : percent > 0 ? `Owner pays ${100 - percent}% of the plan price` : undefined}
        >
          {(id) => (
            <Input id={id} required type="number" min={1} max={100} step={1} value={form.percent_off} onChange={(e) => set({ percent_off: e.target.value })} />
          )}
        </FormField>
        <FormField label="Description (optional)" className="sm:col-span-2" error={err("description")}>
          {(id) => (
            <Input id={id} maxLength={200} placeholder="e.g. Launch offer for new turfs" value={form.description} onChange={(e) => set({ description: e.target.value })} />
          )}
        </FormField>
        <FormField label="Valid from (optional)" error={err("valid_from")}>
          {(id) => <Input id={id} type="date" value={form.valid_from} onChange={(e) => set({ valid_from: e.target.value })} />}
        </FormField>
        <FormField label="Valid until (optional)" error={err("valid_until")}>
          {(id) => <Input id={id} type="date" value={form.valid_until} onChange={(e) => set({ valid_until: e.target.value })} />}
        </FormField>
        <FormField label="Total uses (optional)" hint="Empty = unlimited" error={err("max_uses")}>
          {(id) => (
            <Input id={id} type="number" min={1} step={1} placeholder="Unlimited" value={form.max_uses} onChange={(e) => set({ max_uses: e.target.value })} />
          )}
        </FormField>
        <div className="flex items-center pt-6">
          <Checkbox label="Code is on (owners can use it)" checked={form.is_active} onChange={(e) => set({ is_active: e.target.checked })} />
        </div>
        {save.error && !fields && <p className="text-sm text-destructive sm:col-span-2">{errorText(save.error)}</p>}
        <Button type="submit" disabled={save.isPending} className="sm:col-span-2 sm:justify-self-end">
          {save.isPending && <Loader2 className="animate-spin" />} {isNew ? "Create promo code" : "Save"}
        </Button>
      </form>
    </Dialog>
  );
}
