import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <svg viewBox="0 0 32 32" className="size-8" aria-hidden>
        <rect width="32" height="32" rx="8" className="fill-primary" />
        <path d="M8 10h16v3h-6.5v11h-3V13H8z" className="fill-accent" />
      </svg>
      <span className="font-display text-2xl font-extrabold tracking-wide">TURFOS</span>
    </span>
  );
}
