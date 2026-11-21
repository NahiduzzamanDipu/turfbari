import { X } from "lucide-react";
import * as React from "react";
import { useEffect, useId } from "react";
import { cn } from "@/lib/utils";

const control =
  "w-full rounded-md border border-input bg-card px-3 text-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/30 disabled:opacity-60 aria-invalid:border-destructive";

export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return <input className={cn(control, "h-11", className)} {...props} />;
}

export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return <textarea className={cn(control, "min-h-20 py-2", className)} {...props} />;
}

export function Select({ className, ...props }: React.ComponentProps<"select">) {
  return <select className={cn(control, "h-11 pr-8", className)} {...props} />;
}

export function Label({ className, ...props }: React.ComponentProps<"label">) {
  return <label className={cn("text-sm font-medium", className)} {...props} />;
}

/** Label + control + help/error text. Pass the control as a render function to receive its id. */
export function FormField({
  label,
  error,
  hint,
  className,
  children,
}: {
  label: string;
  error?: string | string[] | null;
  hint?: string;
  className?: string;
  children: (id: string) => React.ReactNode;
}) {
  const id = useId();
  const message = Array.isArray(error) ? error[0] : error;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children(id)}
      {message ? (
        <p className="text-xs text-destructive">{message}</p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}

export function Checkbox({ label, className, ...props }: React.ComponentProps<"input"> & { label: string }) {
  return (
    <label className={cn("inline-flex cursor-pointer items-center gap-2 text-sm", className)}>
      <input type="checkbox" className="size-4 accent-[var(--primary)]" {...props} />
      {label}
    </label>
  );
}

const BADGE_TONES = {
  neutral: "bg-secondary text-secondary-foreground",
  green: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200",
  amber: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
  red: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-200",
  blue: "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200",
  lime: "bg-accent text-accent-foreground",
} as const;

export type BadgeTone = keyof typeof BADGE_TONES;

export function Badge({
  tone = "neutral",
  className,
  ...props
}: React.ComponentProps<"span"> & { tone?: BadgeTone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold",
        BADGE_TONES[tone],
        className,
      )}
      {...props}
    />
  );
}

export const STATUS_TONE: Record<string, BadgeTone> = {
  pending: "amber",
  confirmed: "blue",
  completed: "green",
  cancelled: "neutral",
  rejected: "red",
  no_show: "red",
  expired: "neutral",
  paid: "green",
  partial: "amber",
  unpaid: "red",
  active: "green",
  suspended: "red",
  archived: "neutral",
  contacted: "blue",
  approved: "green",
};

/** Accessible modal dialog. Closes on Escape and backdrop click. */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4">
      <button
        type="button"
        aria-label="Close dialog"
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cn(
          "relative max-h-[96dvh] w-full overflow-y-auto rounded-t-2xl border bg-background p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] shadow-xl sm:max-h-[92dvh] sm:rounded-xl sm:p-5",
          wide ? "sm:max-w-2xl" : "sm:max-w-lg",
        )}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h2 id={titleId} className="text-lg font-semibold">
              {title}
            </h2>
            {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-secondary"
            aria-label="Close"
          >
            <X className="size-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  children,
}: {
  icon?: React.ReactNode;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-8 text-center">
      {icon && <div className="text-muted-foreground [&_svg]:size-8">{icon}</div>}
      <p className="font-semibold">{title}</p>
      {children && <div className="max-w-sm text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-2 px-4 py-8 text-center text-sm">
      <p className="font-semibold">Couldn't load this</p>
      <p className="text-muted-foreground">{error.message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="font-semibold text-primary hover:underline">
          Try again
        </button>
      )}
    </div>
  );
}

function visibleText(node: React.ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(visibleText).join("");
  if (React.isValidElement<{ children?: React.ReactNode }>(node)) return visibleText(node.props.children);
  return "";
}

export function Table({ className, children, ...props }: React.ComponentProps<"table">) {
  const parts = React.Children.toArray(children);
  const head = parts.find((part) => React.isValidElement(part) && part.type === "thead");
  const headRow = head && React.isValidElement<{ children?: React.ReactNode }>(head)
    ? React.Children.toArray(head.props.children).find((row) => React.isValidElement(row) && row.type === "tr")
    : undefined;
  const labels = headRow && React.isValidElement<{ children?: React.ReactNode }>(headRow)
    ? React.Children.toArray(headRow.props.children).map(visibleText)
    : [];
  const responsiveParts = parts.map((part) => {
    if (!React.isValidElement<{ children?: React.ReactNode }>(part) || part.type !== "tbody") return part;
    return React.cloneElement(
      part,
      undefined,
      React.Children.map(part.props.children, (row) => {
        if (!React.isValidElement<{ children?: React.ReactNode }>(row) || row.type !== "tr") return row;
        let cellIndex = 0;
        return React.cloneElement(
          row,
          undefined,
          React.Children.map(row.props.children, (cell) => {
            if (!React.isValidElement<{ children?: React.ReactNode; "data-label"?: string }>(cell) || cell.type !== "td") return cell;
            const label = labels[cellIndex++]?.trim();
            return label ? React.cloneElement(cell, { "data-label": label }) : cell;
          }),
        );
      }),
    );
  });

  return (
    <div className="overflow-x-auto">
      <table
        className={cn(
          "responsive-table w-full text-left text-sm [&_td]:px-2.5 [&_td]:py-2 [&_th]:whitespace-nowrap [&_th]:px-2.5 [&_th]:py-1.5 [&_th]:text-xs [&_th]:font-medium [&_th]:text-muted-foreground [&_tbody_tr]:border-t",
          className,
        )}
        {...props}
      >
        {responsiveParts}
      </table>
    </div>
  );
}
