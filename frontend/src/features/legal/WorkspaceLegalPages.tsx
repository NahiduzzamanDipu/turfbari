import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, FileText, Layers, Loader2, LogOut, Scale, Store } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import { PageHeader } from "@/components/layout/AppShell";
import { type Lang, LangToggle, LegalBody, legalDate, legalDateTime, legalTitle } from "@/components/legal/Legal";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, EmptyState, ErrorState, Table } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { FullPageSpinner, meKey, useLogout, useMe } from "@/features/auth/auth";
import { ApiError, api } from "@/lib/api";
import type { LegalEntry, LegalVersionBody } from "@/lib/types";

interface LegalStatus {
  pending: LegalVersionBody[];
  documents: LegalEntry[];
  history: {
    id: number;
    accepted_at: string;
    document: string;
    category: string;
    sector: string | null;
    version: number;
    version_id: number;
    action: string;
    action_label: string;
    turf: string | null;
    booking: string | null;
    related_ref: string;
  }[];
  sector: { slug: string; name_en: string; name_bn: string } | null;
  business: { name: string | null; cancellation_policy: string } | null;
}

const statusKey = ["legal", "status"] as const;
const useLegalStatus = () => useQuery({ queryKey: statusKey, queryFn: () => api<LegalStatus>("/legal/status/") });

/**
 * Full-screen sign-in gate: shown instead of the workspace while updated mandatory documents are
 * unaccepted. The API refuses workspace calls until then, so this is not just a UI step.
 */
export function LegalGatePage() {
  const me = useMe();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const logout = useLogout();
  const status = useLegalStatus();
  const [agree, setAgree] = useState(false);
  const [lang, setLang] = useState<Lang>("bn");
  const accept = useMutation({
    mutationFn: () =>
      api<{ accepted: number }>("/legal/accept/", {
        method: "POST",
        json: { agree, accepted_versions: (status.data?.pending ?? []).map((d) => d.version_id) },
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: meKey });
      const next = params.get("next");
      navigate(next?.startsWith("/workspace") ? next : "/workspace", { replace: true });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.fields?.code?.[0] === "legal_versions_changed") {
        setAgree(false);
        void status.refetch();
      }
    },
  });

  if (me.isPending) return <FullPageSpinner />;
  if (!me.data?.authenticated) return <Navigate to="/login" replace />;
  if (me.data.user?.must_change_password) return <Navigate to="/set-password" replace />;
  if (!me.data.user?.legal_pending) return <Navigate to={me.data.home} replace />;

  const pending = status.data?.pending ?? [];
  return (
    <div className="min-h-dvh bg-secondary/40 px-4 py-8">
      <div className="mx-auto flex max-w-3xl flex-col gap-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold">
              <Scale className="size-6 text-primary" />
              {lang === "bn" ? "হালনাগাদকৃত শর্তাবলী" : "Updated terms & policies"}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {lang === "bn"
                ? "ড্যাশবোর্ড চালিয়ে যেতে নিচের ডকুমেন্টগুলো পড়ে সম্মতি দিন।"
                : "Please read and accept the documents below to continue to your dashboard."}
            </p>
          </div>
          <LangToggle lang={lang} onChange={setLang} />
        </div>
        {status.isPending && <Skeleton className="h-96" />}
        {status.isError && <ErrorState error={status.error} onRetry={() => status.refetch()} />}
        {pending.map((d) => (
          <Card key={d.version_id}>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2">
                {legalTitle(d, lang)}
                <Badge tone={d.scope === "sector" ? "blue" : "neutral"}>
                  {d.scope === "sector" ? (lang === "bn" ? d.sector_name_bn || d.sector_name_en : d.sector_name_en) : "TurfBari"}
                </Badge>
              </CardTitle>
              <CardDescription>
                v{d.version} · {lang === "bn" ? "কার্যকর" : "effective"} {legalDate(d.effective_at)}
                {d.change_summary && ` · ${d.change_summary}`}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="max-h-80 overflow-y-auto rounded-md border bg-background p-4 text-sm">
                <LegalBody doc={d} lang={lang} />
              </div>
            </CardContent>
          </Card>
        ))}
        {status.data && (
          <Card>
            <CardContent className="flex flex-col gap-4 py-5">
              <label className="flex items-start gap-2 text-sm" htmlFor="gate-agree">
                <input
                  id="gate-agree"
                  type="checkbox"
                  className="mt-1 size-4 shrink-0 accent-[var(--primary)]"
                  checked={agree}
                  onChange={(e) => setAgree(e.target.checked)}
                />
                <span lang="bn">
                  আমি উপরের সব ডকুমেন্ট পড়েছি এবং সম্মত হয়েছি।{" "}
                  <span className="text-muted-foreground" lang="en">
                    I have read and agree to all the documents above.
                  </span>
                </span>
              </label>
              {accept.error && <p className="text-sm text-destructive">{accept.error.message}</p>}
              <div className="flex flex-wrap gap-2">
                <Button disabled={!agree || accept.isPending || pending.length === 0} onClick={() => accept.mutate()}>
                  {accept.isPending ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
                  {lang === "bn" ? "সম্মতি দিয়ে চালিয়ে যান" : "Accept and continue"}
                </Button>
                <Button variant="ghost" onClick={() => logout.mutate()}>
                  <LogOut /> {lang === "bn" ? "সাইন আউট" : "Sign out"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

/** Owner/manager "Legal & Policies": what applies to this business, and what they accepted. */
export function LegalPoliciesPage() {
  const status = useLegalStatus();
  if (status.isPending) return <Skeleton className="h-96" />;
  if (status.isError) return <ErrorState error={status.error} onRetry={() => status.refetch()} />;
  const { documents, history, sector, business } = status.data;
  const platform = documents.filter((d) => d.scope === "platform");
  const sectorDocs = documents.filter((d) => d.scope === "sector");
  const row = (d: LegalEntry) => (
    <li key={d.document_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
      <Link to={d.url} target="_blank" className="inline-flex items-center gap-1 font-medium hover:underline">
        {d.title_en}
        {d.title_bn && <span className="text-muted-foreground">· {d.title_bn}</span>}
        <ExternalLink className="size-3" />
      </Link>
      <span className="text-xs text-muted-foreground">
        v{d.version} · effective {legalDate(d.effective_at)}
      </span>
    </li>
  );
  return (
    <>
      <PageHeader
        title="Legal & Policies"
        description="The TurfBari terms and policies that apply to your business, and your acceptance history. Platform documents are managed by TurfBari and can't be edited here."
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="size-5 text-primary" /> Platform policies
            </CardTitle>
            <CardDescription>Apply to every business on TurfBari.</CardDescription>
          </CardHeader>
          <CardContent>
            {platform.length ? <ul className="divide-y text-sm">{platform.map(row)}</ul> : <p className="text-sm text-muted-foreground">None published.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Layers className="size-5 text-primary" /> Sector policies
            </CardTitle>
            <CardDescription>{sector ? `${sector.name_en}${sector.name_bn ? ` · ${sector.name_bn}` : ""}` : "No sector"} — in addition to the platform policies.</CardDescription>
          </CardHeader>
          <CardContent>
            {sectorDocs.length ? <ul className="divide-y text-sm">{sectorDocs.map(row)}</ul> : <p className="text-sm text-muted-foreground">None published for this sector.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Store className="size-5 text-primary" /> Your business policy
            </CardTitle>
            <CardDescription>Your own cancellation policy, shown to your customers. It can't override TurfBari's terms.</CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            {business?.cancellation_policy ? (
              <p className="whitespace-pre-line">{business.cancellation_policy}</p>
            ) : (
              <p className="text-muted-foreground">Not set.</p>
            )}
            <Link to="/workspace/settings" className="mt-2 inline-block font-medium text-primary hover:underline">
              Edit in Settings
            </Link>
          </CardContent>
        </Card>
      </div>
      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Your acceptance history</CardTitle>
          <CardDescription>Every version you agreed to, with the time (Bangladesh time) and where.</CardDescription>
        </CardHeader>
        <CardContent>
          {history.length === 0 ? (
            <EmptyState title="No acceptances yet" />
          ) : (
            <Table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Document</th>
                  <th>Version</th>
                  <th>Where</th>
                  <th>Business</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id}>
                    <td className="whitespace-nowrap">{legalDateTime(h.accepted_at)}</td>
                    <td>
                      {h.document}
                      {h.sector && <span className="text-muted-foreground"> · {h.sector}</span>}
                    </td>
                    <td>v{h.version}</td>
                    <td>{h.action_label}</td>
                    <td>{h.turf ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}
