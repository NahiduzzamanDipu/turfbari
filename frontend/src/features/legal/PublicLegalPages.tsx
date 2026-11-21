import { useQuery } from "@tanstack/react-query";
import { ChevronRight, FileText, History, Layers, Scale } from "lucide-react";
import { useEffect } from "react";
import { Link, NavLink, useParams, useSearchParams } from "react-router";
import { type Lang, LegalBody, legalDate, legalTitle } from "@/components/legal/Legal";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import type { LegalEntry, LegalHistoryItem, LegalVersionBody } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/lib/i18n";

interface LegalIndex {
  documents: LegalEntry[];
  sectors: { id: string; slug: string; name_en: string; name_bn: string; documents: LegalEntry[] }[];
}

function useLang(): Lang {
  return useLanguage().language;
}

function useLegalIndex() {
  return useQuery({ queryKey: ["public", "legal"], queryFn: () => api<LegalIndex>("/public/legal/"), staleTime: 60_000 });
}

/** Left-hand navigation of every published document (platform first, then each sector). */
function LegalNav({ lang }: { lang: Lang }) {
  const index = useLegalIndex();
  if (!index.data) return <Skeleton className="h-64" />;
  const item = "flex items-center justify-between gap-2 rounded-md px-3 py-2 text-sm transition hover:bg-secondary";
  return (
    <nav aria-label="Legal documents" className="flex flex-col gap-4">
      <div>
        <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {lang === "bn" ? "প্ল্যাটফর্ম" : "Platform"}
        </p>
        {index.data.documents.map((d) => (
          <NavLink key={d.document_id} to={d.url} className={({ isActive }) => cn(item, isActive && "bg-secondary font-semibold")}>
            {legalTitle(d, lang)}
          </NavLink>
        ))}
      </div>
      {index.data.sectors
        .filter((s) => s.documents.length > 0)
        .map((s) => (
          <div key={s.slug}>
            <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {lang === "bn" ? s.name_bn || s.name_en : s.name_en}
            </p>
            <NavLink to={`/legal/sector/${s.slug}`} className={({ isActive }) => cn(item, isActive && "bg-secondary font-semibold")}>
              {lang === "bn" ? "সেক্টরের শর্তাবলী ও নিয়ম" : "Sector terms & rules"}
            </NavLink>
          </div>
        ))}
    </nav>
  );
}

function LegalShell({ children, lang }: { children: React.ReactNode; lang: Lang }) {
  return (
    <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 lg:grid-cols-[16rem_1fr]">
      <aside className="order-2 lg:order-1">
        <div className="lg:sticky lg:top-20">
          <Link to="/legal" className="mb-3 flex items-center gap-2 px-3 font-semibold">
            <Scale className="size-4 text-primary" /> {lang === "bn" ? "আইনি তথ্য কেন্দ্র" : "Legal centre"}
          </Link>
          <LegalNav lang={lang} />
        </div>
      </aside>
      <div className="order-1 min-w-0 lg:order-2">
        <div className="mb-4 flex justify-end">
        </div>
        {children}
      </div>
    </div>
  );
}

function DocMeta({ doc, lang }: { doc: LegalVersionBody; lang: Lang }) {
  const bn = lang === "bn";
  return (
    <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
      <div>
        <dt className="inline">{bn ? "সংস্করণ" : "Version"} </dt>
        <dd className="inline font-semibold text-foreground">{doc.version}</dd>
      </div>
      <div>
        <dt className="inline">{bn ? "কার্যকর" : "Effective"} </dt>
        <dd className="inline font-semibold text-foreground">{legalDate(doc.effective_at)}</dd>
      </div>
      <div>
        <dt className="inline">{bn ? "সর্বশেষ হালনাগাদ" : "Last updated"} </dt>
        <dd className="inline font-semibold text-foreground">{legalDate(doc.published_at)}</dd>
      </div>
    </dl>
  );
}

function VersionHistory({ history, current, base, lang }: { history: LegalHistoryItem[]; current: number; base: string; lang: Lang }) {
  if (history.length < 2) return null;
  return (
    <details className="mt-8 rounded-lg border p-4 text-sm">
      <summary className="flex cursor-pointer items-center gap-2 font-semibold">
        <History className="size-4" /> {lang === "bn" ? "আগের সংস্করণ" : "Previous versions"}
      </summary>
      <ul className="mt-3 flex flex-col gap-2">
        {history.map((h, i) => (
          <li key={h.version} className="flex flex-wrap items-center justify-between gap-2">
            <Link
              to={i === 0 && !h.withdrawn ? base : `${base}?version=${h.version}`}
              className={cn("font-medium hover:underline", h.version === current && "text-primary")}
            >
              v{h.version} · {legalDate(h.effective_at)}
              {h.withdrawn && <span className="ml-1 text-xs text-muted-foreground">(withdrawn)</span>}
            </Link>
            {h.change_summary && <span className="text-xs text-muted-foreground">{h.change_summary}</span>}
          </li>
        ))}
      </ul>
    </details>
  );
}

/** /legal — overview of every published platform and sector document. */
export function LegalIndexPage() {
  const lang = useLang();
  const index = useLegalIndex();
  useEffect(() => {
    document.title = "Legal centre · TurfBari";
  }, []);
  return (
    <LegalShell lang={lang}>
      <h1 className="font-display text-4xl font-extrabold uppercase">{lang === "bn" ? "শর্তাবলী ও নীতিমালা" : "Terms & policies"}</h1>
      <p className="mt-2 text-muted-foreground">
        {lang === "bn"
          ? "TurfBari ব্যবহারের সব শর্ত, নিয়ম ও নীতি এক জায়গায়। সেক্টরভিত্তিক নিয়মগুলো প্ল্যাটফর্মের সাধারণ শর্তের সাথে যুক্ত হয় — বদলায় না।"
          : "Every term, rule and policy for using TurfBari in one place. Sector rules add to the platform terms — they never replace them."}
      </p>
      {index.isPending && <Skeleton className="mt-6 h-64" />}
      {index.isError && <ErrorState error={index.error} onRetry={() => index.refetch()} />}
      {index.data && index.data.documents.length === 0 && index.data.sectors.every((s) => s.documents.length === 0) && (
        <EmptyState icon={<FileText />} title={lang === "bn" ? "এখনো কোনো ডকুমেন্ট প্রকাশিত হয়নি" : "Nothing published yet"} />
      )}
      {index.data && (
        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          {index.data.documents.map((d) => (
            <Link key={d.document_id} to={d.url}>
              <Card className="h-full transition hover:border-primary">
                <CardContent className="flex items-center justify-between gap-3 py-4">
                  <div>
                    <p className="font-semibold">{legalTitle(d, lang)}</p>
                    <p className="text-xs text-muted-foreground">
                      v{d.version} · {legalDate(d.effective_at)}
                    </p>
                  </div>
                  <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                </CardContent>
              </Card>
            </Link>
          ))}
          {index.data.sectors
            .filter((s) => s.documents.length > 0)
            .map((s) => (
              <Link key={s.slug} to={`/legal/sector/${s.slug}`}>
                <Card className="h-full transition hover:border-primary">
                  <CardContent className="flex items-center justify-between gap-3 py-4">
                    <div>
                      <p className="flex items-center gap-2 font-semibold">
                        <Layers className="size-4 text-primary" /> {lang === "bn" ? s.name_bn || s.name_en : s.name_en}
                      </p>
                      <p className="text-xs text-muted-foreground">{s.documents.map((d) => legalTitle(d, lang)).join(" · ")}</p>
                    </div>
                    <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                  </CardContent>
                </Card>
              </Link>
            ))}
        </div>
      )}
    </LegalShell>
  );
}

/** /legal/:slug — one platform document (current version, or ?version=N). */
export function LegalDocumentPage() {
  const { slug = "" } = useParams();
  const [params] = useSearchParams();
  const version = params.get("version");
  const lang = useLang();
  const doc = useQuery({
    queryKey: ["public", "legal", slug, version],
    queryFn: () =>
      api<LegalVersionBody & { is_current: boolean; history: LegalHistoryItem[] }>(
        `/public/legal/${encodeURIComponent(slug)}/${version ? `?version=${encodeURIComponent(version)}` : ""}`,
      ),
    retry: false,
  });
  useEffect(() => {
    if (doc.data) document.title = `${legalTitle(doc.data, "en")} · TurfBari`;
  }, [doc.data]);
  const missing = doc.error instanceof ApiError && doc.error.status === 404;
  return (
    <LegalShell lang={lang}>
      {doc.isPending && <Skeleton className="h-96" />}
      {missing && (
        <EmptyState icon={<FileText />} title={lang === "bn" ? "এই ডকুমেন্টটি এখনো প্রকাশিত হয়নি" : "This document hasn't been published yet"} />
      )}
      {doc.isError && !missing && <ErrorState error={doc.error} onRetry={() => doc.refetch()} />}
      {doc.data && (
        <article>
          {!doc.data.is_current && (
            <p className="mb-4 rounded-md bg-amber-100 px-3 py-2 text-sm text-amber-900 dark:bg-amber-500/15 dark:text-amber-200">
              {lang === "bn" ? "আপনি একটি পুরনো সংস্করণ দেখছেন।" : "You are viewing an earlier version."}{" "}
              <Link to={`/legal/${slug}`} className="font-semibold underline">
                {lang === "bn" ? "বর্তমান সংস্করণ" : "See the current version"}
              </Link>
            </p>
          )}
          <h1 className="font-display text-3xl font-extrabold uppercase sm:text-4xl">{legalTitle(doc.data, lang)}</h1>
          <DocMeta doc={doc.data} lang={lang} />
          <div className="mt-6">
            <LegalBody doc={doc.data} lang={lang} />
          </div>
          <VersionHistory history={doc.data.history} current={doc.data.version} base={`/legal/${slug}`} lang={lang} />
        </article>
      )}
    </LegalShell>
  );
}

/** /legal/sector/:slug — a sector's own terms/rules plus the platform documents they build on. */
export function SectorLegalPage() {
  const { slug = "" } = useParams();
  const lang = useLang();
  const data = useQuery({
    queryKey: ["public", "legal", "sector", slug],
    queryFn: () =>
      api<{
        sector: { slug: string; name_en: string; name_bn: string };
        documents: (LegalVersionBody & { history: LegalHistoryItem[] })[];
        inherited: LegalEntry[];
      }>(`/public/legal/sector/${encodeURIComponent(slug)}/`),
    retry: false,
  });
  const missing = data.error instanceof ApiError && data.error.status === 404;
  const name = data.data ? (lang === "bn" ? data.data.sector.name_bn || data.data.sector.name_en : data.data.sector.name_en) : "";
  return (
    <LegalShell lang={lang}>
      {data.isPending && <Skeleton className="h-96" />}
      {missing && <EmptyState icon={<FileText />} title={lang === "bn" ? "সেক্টর পাওয়া যায়নি" : "Sector not found"} />}
      {data.isError && !missing && <ErrorState error={data.error} onRetry={() => data.refetch()} />}
      {data.data && (
        <div className="flex flex-col gap-8">
          <div>
            <h1 className="font-display text-3xl font-extrabold uppercase sm:text-4xl">{name}</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {lang === "bn"
                ? "এই সেক্টরের ব্যবসার জন্য অতিরিক্ত শর্ত ও নিয়ম। প্ল্যাটফর্মের সাধারণ শর্তাবলী সবসময় প্রযোজ্য থাকে:"
                : "Additional terms and rules for businesses in this sector. The platform terms always apply as well:"}
            </p>
            <ul className="mt-2 flex flex-wrap gap-2">
              {data.data.inherited.map((d) => (
                <li key={d.document_id}>
                  <Link to={d.url} className="rounded-full border px-3 py-1 text-xs font-medium hover:bg-secondary">
                    {legalTitle(d, lang)}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          {data.data.documents.length === 0 && (
            <EmptyState icon={<FileText />} title={lang === "bn" ? "এই সেক্টরের কোনো আলাদা নিয়ম প্রকাশিত হয়নি" : "No sector-specific documents yet"} />
          )}
          {data.data.documents.map((d) => (
            <article key={d.document_id} id={d.category} className="scroll-mt-24 border-t pt-6">
              <h2 className="text-2xl font-bold">{legalTitle(d, lang)}</h2>
              <DocMeta doc={d} lang={lang} />
              <div className="mt-4">
                <LegalBody doc={d} lang={lang} />
              </div>
            </article>
          ))}
        </div>
      )}
    </LegalShell>
  );
}
