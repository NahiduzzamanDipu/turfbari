import { useQuery } from "@tanstack/react-query";
import { Mail, MapPin, Phone, ChevronRight, FileText, History, Layers, Printer, Scale, Share2 } from "lucide-react";
import { useEffect, useMemo } from "react";
import { Link, NavLink, useParams, useSearchParams } from "react-router";
import { type Lang, LangToggle, LegalBody, LegalHtml, legalDate, legalTitle } from "@/components/legal/Legal";
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

export function linkedSections(html: string) {
  const parsed = new DOMParser().parseFromString(html, "text/html");
  const sections = Array.from(parsed.body.querySelectorAll("h2")).map((heading, index) => {
    const id = `legal-section-${index + 1}`;
    heading.id = id;
    return { id, title: heading.textContent?.trim() || `Section ${index + 1}` };
  });
  return { html: parsed.body.innerHTML, sections };
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
    <div className="legal-shell mx-auto grid max-w-6xl gap-8 px-4 py-10 lg:grid-cols-[16rem_1fr]">
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
  const { language: lang, setLanguage, canSwitch } = useLanguage();
  const doc = useQuery({
    queryKey: ["public", "legal", slug, version],
    queryFn: () =>
      api<LegalVersionBody & { is_current: boolean; history: LegalHistoryItem[] }>(
        `/public/legal/${encodeURIComponent(slug)}/${version ? `?version=${encodeURIComponent(version)}` : ""}`,
      ),
    retry: false,
  });
  const contact = useQuery({
    queryKey: ["public", "contact"],
    queryFn: () => api<{ enabled: boolean; phone: string | null; email: string | null; facebook_url: string | null; address: string | null }>("/public/contact/"),
    staleTime: 5 * 60_000,
  });
  const wantedBody = doc.data ? (lang === "bn" ? doc.data.body_bn : doc.data.body_en) : "";
  const otherBody = doc.data ? (lang === "bn" ? doc.data.body_en : doc.data.body_bn) : "";
  const bodyUnavailable = !wantedBody.trim() && Boolean(otherBody.trim());
  const body = wantedBody.trim() ? wantedBody : otherBody;
  const bodyLang: Lang = wantedBody.trim() ? lang : lang === "bn" ? "en" : "bn";
  useEffect(() => {
    if (!doc.data) return;
    document.title = `${legalTitle(doc.data, lang)} · TurfBari`;
    document.documentElement.lang = lang;
    let description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!description) {
      description = document.createElement("meta");
      description.name = "description";
      document.head.append(description);
    }
    const localizedBody = lang === "bn" ? doc.data.body_bn : doc.data.body_en;
    const fallbackBody = localizedBody.trim() ? localizedBody : lang === "bn" ? doc.data.body_en : doc.data.body_bn;
    description.content = new DOMParser().parseFromString(fallbackBody, "text/html").body.textContent?.slice(0, 250) ?? document.title;
  }, [doc.data, lang]);
  const prepared = useMemo(
    () => (body ? linkedSections(body) : { html: "", sections: [] as { id: string; title: string }[] }),
    [body],
  );
  const missing = doc.error instanceof ApiError && doc.error.status === 404;
  return (
    <LegalShell lang={lang}>
      {doc.isPending && <Skeleton className="h-96" />}
      {missing && (
        <EmptyState icon={<FileText />} title={lang === "bn" ? "এই ডকুমেন্টটি এখনো প্রকাশিত হয়নি" : "This document hasn't been published yet"} />
      )}
      {doc.isError && !missing && <ErrorState error={doc.error} onRetry={() => doc.refetch()} />}
      {doc.data && (
        <article className="legal-document">
          {!doc.data.is_current && (
            <p className="mb-4 rounded-md bg-amber-100 px-3 py-2 text-sm text-amber-900 dark:bg-amber-500/15 dark:text-amber-200">
              {lang === "bn" ? "আপনি একটি পুরনো সংস্করণ দেখছেন।" : "You are viewing an earlier version."}{" "}
              <Link to={`/legal/${slug}`} className="font-semibold underline">
                {lang === "bn" ? "বর্তমান সংস্করণ" : "See the current version"}
              </Link>
            </p>
          )}
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="font-display text-3xl font-extrabold uppercase sm:text-4xl">{legalTitle(doc.data, lang)}</h1>
              <DocMeta doc={doc.data} lang={lang} />
            </div>
            <div className="flex flex-wrap items-center gap-2 print:hidden">
              {canSwitch && <LangToggle lang={lang} onChange={setLanguage} />}
              <button
                type="button"
                onClick={() => window.print()}
                className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                <Printer className="size-4" /> {lang === "bn" ? "প্রিন্ট করুন" : "Print"}
              </button>
            </div>
          </div>
          {prepared.sections.length > 0 && (
            <nav
              aria-label={lang === "bn" ? "এই পাতার বিষয়বস্তু" : "On this page"}
              className="mt-5 rounded-xl border bg-card p-4 print:hidden"
            >
              <h2 className="mb-2 text-sm font-semibold">{lang === "bn" ? "এই পাতার বিষয়বস্তু" : "On this page"}</h2>
              <ol className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                {prepared.sections.map((section, index) => (
                  <li key={section.id}>
                    <a
                      className="text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2"
                      href={`#${section.id}`}
                    >
                      {index + 1}. {section.title.replace(/^\d+[.)]\s*/, "")}
                    </a>
                  </li>
                ))}
              </ol>
            </nav>
          )}
          <div className="mt-6">
            {bodyUnavailable && (
              <p className="mb-3 rounded-md bg-secondary px-3 py-2 text-xs text-muted-foreground">
                {lang === "bn" ? "এই নথির বাংলা সংস্করণ নেই — ইংরেজি সংস্করণ দেখানো হচ্ছে।" : "This document is not available in English yet — showing the Bengali version."}
              </p>
            )}
            <LegalHtml html={prepared.html} lang={bodyLang} />
          </div>
          <nav
            aria-label={lang === "bn" ? "সম্পর্কিত নীতি" : "Related policies"}
            className="mt-8 flex flex-wrap gap-4 border-t pt-4 text-sm print:hidden"
          >
            <Link className="text-primary underline-offset-4 hover:underline" to="/legal/privacy">
              {lang === "bn" ? "গোপনীয়তা নীতি" : "Privacy Policy"}
            </Link>
            <Link className="text-primary underline-offset-4 hover:underline" to="/legal">
              {lang === "bn" ? "সব আইনি নথি" : "All legal documents"}
            </Link>
          </nav>
          {slug === "terms" && contact.data?.enabled && (contact.data.phone || contact.data.email || contact.data.facebook_url || contact.data.address) && (
            <section className="mt-6 rounded-xl border bg-secondary/40 p-4" aria-labelledby="legal-contact-title">
              <h2 id="legal-contact-title" className="font-semibold">{lang === "bn" ? "TurfBari-এর সঙ্গে যোগাযোগ" : "Contact TURFBARI"}</h2>
              <ul className="mt-3 flex flex-col gap-2 text-sm">
                {contact.data.phone && <li><a className="inline-flex items-center gap-2 hover:underline" href={`tel:${contact.data.phone.replace(/[^+\d]/g, "")}`}><Phone className="size-4" />{contact.data.phone}</a></li>}
                {contact.data.email && <li><a className="inline-flex items-center gap-2 hover:underline" href={`mailto:${contact.data.email}`}><Mail className="size-4" />{contact.data.email}</a></li>}
                {contact.data.facebook_url && <li><a className="inline-flex items-center gap-2 hover:underline" href={contact.data.facebook_url} target="_blank" rel="noopener noreferrer"><Share2 className="size-4" />{lang === "bn" ? "TurfBari Facebook পেজ" : "TurfBari Facebook page"}</a></li>}
                {contact.data.address && <li className="inline-flex items-center gap-2"><MapPin className="size-4" />{contact.data.address}</li>}
              </ul>
            </section>
          )}
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
