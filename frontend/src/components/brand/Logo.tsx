import { useId } from "react";
import { cn } from "@/lib/utils";

const ROTATIONS = [0, 72, 144, 216, 288];
// Flat football: dark centre pentagon, five seams, five rim pentagons showing as caps at the edge.
const CENTER_PENTAGON = "0,-2.6 2.473,-0.803 1.528,2.103 -1.528,2.103 -2.473,-0.803";
const RIM_PENTAGON = "0,2.6 -2.473,0.803 -1.528,-2.103 1.528,-2.103 2.473,0.803";

/**
 * TurfBari mark: a বাড়ি (home) roof sheltering a football — "every turf's home".
 * Pure geometry on a 32-unit grid so it stays crisp from 16px favicons up to app icons.
 * Keep in sync with public/favicon.svg.
 */
export function LogoMark({ className }: { className?: string }) {
  const clip = useId();
  return (
    <svg viewBox="0 0 32 32" className={cn("size-8 shrink-0", className)} aria-hidden>
      <defs>
        <clipPath id={clip}>
          <circle r="6.9" />
        </clipPath>
      </defs>
      <rect width="32" height="32" rx="9" className="fill-primary" />
      <path
        d="M5.5 14.6 16 5.6l10.5 9"
        fill="none"
        strokeWidth="3.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="stroke-accent"
      />
      <g transform="translate(16 20.6)">
        <circle r="6.9" fill="#fff" />
        <g clipPath={`url(#${clip})`} className="fill-primary">
          <polygon points={CENTER_PENTAGON} />
          {ROTATIONS.map((deg) => (
            <g key={deg} transform={`rotate(${deg})`}>
              <line y1="-2.6" y2="-5.4" strokeWidth="1" strokeLinecap="round" className="stroke-primary" />
              <polygon points={RIM_PENTAGON} transform="translate(0 -8)" />
            </g>
          ))}
        </g>
      </g>
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark />
      <span className="font-display text-2xl font-extrabold tracking-wide">
        Turf<span className="text-primary">Bari</span>
      </span>
    </span>
  );
}
