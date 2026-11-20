import type * as React from "react";

/**
 * Renders the admin's Terms text safely — never as HTML. Supported (simple, Bengali-friendly):
 *   # Heading / ## Subheading, "- " or "* " bullets, "1. " numbered items, **bold**, blank line = new paragraph.
 */
function inline(text: string): React.ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? <strong key={i}>{part.slice(2, -2)}</strong> : part,
  );
}

export function FormattedText({ text, className }: { text: string; className?: string }) {
  const blocks: React.ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let para: string[] = [];
  const flushPara = () => {
    if (para.length) blocks.push(<p key={blocks.length}>{inline(para.join(" "))}</p>);
    para = [];
  };
  const flushList = () => {
    if (!list) return;
    const items = list.items.map((it, i) => <li key={i}>{inline(it)}</li>);
    blocks.push(
      list.ordered ? (
        <ol key={blocks.length} className="list-decimal space-y-1 pl-6">
          {items}
        </ol>
      ) : (
        <ul key={blocks.length} className="list-disc space-y-1 pl-6">
          {items}
        </ul>
      ),
    );
    list = null;
  };
  for (const raw of text.replace(/\r\n/g, "\n").split("\n")) {
    const line = raw.trim();
    const bullet = /^[-*•]\s+(.*)$/.exec(line);
    const numbered = /^(\d+|[০-৯]+)[.)]\s+(.*)$/.exec(line);
    if (!line) {
      flushPara();
      flushList();
    } else if (line.startsWith("## ") || line.startsWith("# ")) {
      flushPara();
      flushList();
      const h2 = line.startsWith("# ");
      blocks.push(
        h2 ? (
          <h2 key={blocks.length} className="mt-4 text-xl font-bold">
            {inline(line.slice(2))}
          </h2>
        ) : (
          <h3 key={blocks.length} className="mt-3 text-lg font-semibold">
            {inline(line.slice(3))}
          </h3>
        ),
      );
    } else if (bullet || numbered) {
      flushPara();
      const ordered = Boolean(numbered);
      const item = (numbered ? numbered[2] : bullet![1]) ?? "";
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push(item);
    } else {
      flushList();
      para.push(line);
    }
  }
  flushPara();
  flushList();
  return <div className={className ?? "space-y-3 leading-relaxed"}>{blocks}</div>;
}
