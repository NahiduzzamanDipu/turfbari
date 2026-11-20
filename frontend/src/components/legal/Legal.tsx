import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { Link } from "react-router";
import { api } from "@/lib/api";
import type { LegalEntry, LegalRef } from "@/lib/types";
import { cn } from "@/lib/utils";

const dateFmt = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Dhaka", day: "numeric", month: "long", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Dhaka",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});
/** Bangladesh time, whatever the viewer's device clock says. */
export const legalDate = (iso: string | null | undefined) => (iso ? dateFmt.format(new Date(iso)) : "—");
export const legalDateTime = (iso: string | null | undefined) => (iso ? `${dateTimeFmt.format(new Date(iso))} (BD)` : "—");

export type Lang = "en" | "bn";

/** Title in the chosen language, falling back to the other one. */
export function legalTitle(doc: { title_en: string; title_bn: string }, lang: Lang) {
  return (lang === "bn" ? doc.title_bn || doc.title_en : doc.title_en || doc.title_bn) || "Untitled";
}

/**
 * Renders a legal document body. The HTML was sanitised by the server (allow-list: headings, paragraphs,
 * lists, bold/italic, links, tables) before it was stored, and only server-returned text reaches here.
 */
export function LegalHtml({ html, className, lang }: { html: string; className?: string; lang?: Lang }) {
  return (
    <div
      lang={lang}
      className={cn(
        "legal-body max-w-none space-y-3 leading-relaxed break-words",
        "[&_h2]:mt-6 [&_h2]:text-xl [&_h2]:font-bold [&_h3]:mt-4 [&_h3]:text-lg [&_h3]:font-semibold [&_h4]:mt-3 [&_h4]:font-semibold",
        "[&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-6",
        "[&_a]:font-medium [&_a]:text-primary [&_a]:underline [&_blockquote]:border-l-4 [&_blockquote]:pl-4 [&_blockquote]:text-muted-foreground",
        "[&_hr]:my-4 [&_table]:my-3 [&_table]:w-full [&_table]:border-collapse [&_table]:text-sm",
        "[&_td]:border [&_td]:px-2 [&_td]:py-1.5 [&_th]:border [&_th]:bg-secondary [&_th]:px-2 [&_th]:py-1.5 [&_th]:text-left",
        className,
      )}
      // biome-ignore lint/security/noDangerouslySetInnerHtml: server-sanitised allow-list HTML
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

/** Shows the body in the chosen language, or the other one with a note if this one isn't written. */
export function LegalBody({ doc, lang }: { doc: { body_en: string; body_bn: string }; lang: Lang }) {
  const wanted = lang === "bn" ? doc.body_bn : doc.body_en;
  const other = lang === "bn" ? doc.body_en : doc.body_bn;
  if (wanted.trim()) return <LegalHtml html={wanted} lang={lang} />;
  return (
    <div>
      <p className="mb-3 rounded-md bg-secondary px-3 py-2 text-xs text-muted-foreground">
        {lang === "bn" ? "এই ডকুমেন্টটি এখনো বাংলায় নেই — ইংরেজি সংস্করণ দেখানো হচ্ছে।" : "Not available in English yet — showing the Bengali version."}
      </p>
      <LegalHtml html={other} lang={lang === "bn" ? "en" : "bn"} />
    </div>
  );
}

export function LangToggle({ lang, onChange }: { lang: Lang; onChange: (l: Lang) => void }) {
  return (
    <div className="inline-flex rounded-full border p-0.5 text-sm" role="group" aria-label="Language">
      {(["bn", "en"] as const).map((l) => (
        <button
          key={l}
          type="button"
          aria-pressed={lang === l}
          onClick={() => onChange(l)}
          className={cn("rounded-full px-3 py-1 font-medium transition", lang === l ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}
        >
          {l === "bn" ? "বাংলা" : "English"}
        </button>
      ))}
    </div>
  );
}

/**
 * The single "I agree" checkbox used everywhere an agreement is needed (booking, registration, plan
 * orders, SMS recharges). Lists each required document with a link; unchecked by default.
 */
export function LegalAcceptBox({
  docs,
  checked,
  onChange,
  id = "agree-legal",
  error,
  intro,
}: {
  docs: LegalRef[];
  checked: boolean;
  onChange: (v: boolean) => void;
  id?: string;
  error?: string;
  intro?: string;
}) {
  if (docs.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <div className={cn("flex items-start gap-2 rounded-md border p-3 text-sm", error && "border-destructive")}>
        <input
          id={id}
          type="checkbox"
          required
          className="mt-1 size-4 shrink-0 accent-[var(--primary)]"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          aria-describedby={`${id}-docs`}
        />
        <div className="leading-relaxed">
          <label htmlFor={id} lang="bn" className="cursor-pointer">
            {intro ?? "আমি নিচের শর্তাবলী ও নীতিমালা পড়েছি এবং সম্মত হয়েছি।"}{" "}
            <span className="text-muted-foreground" lang="en">
              I have read and agree to:
            </span>
          </label>
          <ul id={`${id}-docs`} className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
            {docs.map((d) => (
              <li key={d.version_id}>
                <Link to={d.url} target="_blank" className="inline-flex items-center gap-1 font-semibold text-primary hover:underline">
                  {d.title_bn || d.title_en}
                  <span className="font-normal text-muted-foreground">v{d.version}</span>
                  <ExternalLink className="size-3" />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}

/** Documents the signed-in owner/manager still has to accept before a workspace action. */
export function usePendingLegal(action: "subscription" | "sms_recharge" | "account", enabled = true) {
  return useQuery({
    queryKey: ["legal", "pending", action],
    queryFn: () => api<{ documents: LegalEntry[] }>(`/legal/pending/?action=${action}`),
    enabled,
    staleTime: 30_000,
  });
}

/** Body fields to send with a workspace action that may need agreement. */
export function legalPayload(docs: LegalRef[] | undefined, agreed: boolean) {
  return docs && docs.length > 0 ? { agree_legal: agreed, accepted_versions: docs.map((d) => d.version_id) } : {};
}
