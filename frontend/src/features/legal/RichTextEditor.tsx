import {
  Bold,
  Code2,
  Heading2,
  Heading3,
  Italic,
  Link2,
  Link2Off,
  List,
  ListOrdered,
  Minus,
  Pilcrow,
  Quote,
  Redo2,
  Table2,
  Underline,
  Undo2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Textarea } from "@/components/ui/form";
import { cn } from "@/lib/utils";

const TABLE =
  "<table><thead><tr><th>Heading</th><th>Heading</th></tr></thead><tbody><tr><td>Text</td><td>Text</td></tr><tr><td>Text</td><td>Text</td></tr></tbody></table><p></p>";

/**
 * Small rich-text editor for legal documents (headings, paragraphs, lists, bold/italic/underline,
 * links, quotes, tables). Whatever it produces is cleaned again by the server's allow-list before
 * it is stored, so pasted scripts, styles or images never survive.
 */
export function RichTextEditor({
  value,
  onChange,
  lang,
  label,
}: {
  value: string;
  onChange: (html: string) => void;
  lang: "en" | "bn";
  label: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [source, setSource] = useState(false);

  // Only push outside changes into the editable area (typing must not reset the caret).
  useEffect(() => {
    const el = ref.current;
    if (el && !source && el.innerHTML !== value) el.innerHTML = value;
  }, [value, source]);

  const run = (command: string, arg?: string) => {
    ref.current?.focus();
    document.execCommand(command, false, arg);
    if (ref.current) onChange(ref.current.innerHTML);
  };
  const link = () => {
    const url = window.prompt("Link address (https://…, mailto: or tel:)", "https://");
    if (!url) return;
    if (!/^(https?:\/\/|mailto:|tel:)/i.test(url.trim())) {
      window.alert("Only web, email and phone links are allowed.");
      return;
    }
    run("createLink", url.trim());
  };

  const tools: { icon: React.ReactNode; label: string; action: () => void }[] = [
    { icon: <Heading2 />, label: "Heading", action: () => run("formatBlock", "<h2>") },
    { icon: <Heading3 />, label: "Sub-heading", action: () => run("formatBlock", "<h3>") },
    { icon: <Pilcrow />, label: "Paragraph", action: () => run("formatBlock", "<p>") },
    { icon: <Bold />, label: "Bold", action: () => run("bold") },
    { icon: <Italic />, label: "Italic", action: () => run("italic") },
    { icon: <Underline />, label: "Underline", action: () => run("underline") },
    { icon: <List />, label: "Bulleted list", action: () => run("insertUnorderedList") },
    { icon: <ListOrdered />, label: "Numbered list", action: () => run("insertOrderedList") },
    { icon: <Quote />, label: "Quote", action: () => run("formatBlock", "<blockquote>") },
    { icon: <Link2 />, label: "Add link", action: link },
    { icon: <Link2Off />, label: "Remove link", action: () => run("unlink") },
    { icon: <Table2 />, label: "Insert table", action: () => run("insertHTML", TABLE) },
    { icon: <Minus />, label: "Divider", action: () => run("insertHorizontalRule") },
    { icon: <Undo2 />, label: "Undo", action: () => run("undo") },
    { icon: <Redo2 />, label: "Redo", action: () => run("redo") },
  ];

  return (
    <div className="overflow-hidden rounded-md border focus-within:ring-2 focus-within:ring-ring">
      <div role="toolbar" aria-label={`${label} formatting`} className="flex flex-wrap items-center gap-0.5 border-b bg-secondary/60 p-1">
        {tools.map((t) => (
          <button
            key={t.label}
            type="button"
            title={t.label}
            aria-label={t.label}
            disabled={source}
            onMouseDown={(e) => e.preventDefault()}
            onClick={t.action}
            className="rounded p-1.5 text-muted-foreground transition hover:bg-background hover:text-foreground disabled:opacity-40 [&_svg]:size-4"
          >
            {t.icon}
          </button>
        ))}
        <button
          type="button"
          aria-pressed={source}
          onClick={() => setSource((s) => !s)}
          className={cn(
            "ml-auto inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium [&_svg]:size-3.5",
            source ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-background",
          )}
        >
          <Code2 /> HTML
        </button>
      </div>
      {source ? (
        <Textarea
          aria-label={`${label} (HTML)`}
          className="min-h-[24rem] rounded-none border-0 font-mono text-xs focus-visible:ring-0"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <div
          ref={ref}
          role="textbox"
          aria-multiline="true"
          aria-label={label}
          lang={lang}
          contentEditable
          suppressContentEditableWarning
          onInput={(e) => onChange((e.target as HTMLDivElement).innerHTML)}
          className={cn(
            "min-h-[24rem] space-y-3 bg-background p-4 text-sm leading-relaxed outline-none",
            "[&_h2]:text-xl [&_h2]:font-bold [&_h3]:text-lg [&_h3]:font-semibold [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:pl-6",
            "[&_a]:text-primary [&_a]:underline [&_blockquote]:border-l-4 [&_blockquote]:pl-4 [&_table]:w-full [&_td]:border [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:bg-secondary [&_th]:px-2",
          )}
        />
      )}
    </div>
  );
}
