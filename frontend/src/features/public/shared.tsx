import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Division } from "@/lib/types";

export function useLocations() {
  return useQuery({
    queryKey: ["public", "locations"],
    queryFn: () => api<Division[]>("/public/locations/"),
    staleTime: 10 * 60_000,
  });
}

export function useAmenities() {
  return useQuery({
    queryKey: ["public", "amenities"],
    queryFn: () => api<{ name: string; slug: string }[]>("/public/amenities/"),
    staleTime: 10 * 60_000,
  });
}

export function GoogleMapsPin({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path fill="#EA4335" d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7Z" />
      <circle cx="12" cy="9" r="2.6" fill="#fff" />
    </svg>
  );
}

export function TurfArt({ seed, className }: { seed: string; className?: string }) {
  let hash = 0;
  for (const ch of seed) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  const hue = 140 + (hash % 40);
  const angle = hash % 2 ? 0 : 90;
  return (
    <div
      aria-hidden
      className={className}
      style={{
        background: `repeating-linear-gradient(${angle}deg, oklch(0.55 0.13 ${hue}) 0 28px, oklch(0.5 0.13 ${hue}) 28px 56px)`,
      }}
    >
      <svg viewBox="0 0 200 120" className="size-full opacity-60" preserveAspectRatio="none">
        <g fill="none" stroke="white" strokeWidth="1.5">
          <rect x="8" y="8" width="184" height="104" />
          <line x1="100" y1="8" x2="100" y2="112" />
          <circle cx="100" cy="60" r="16" />
          <rect x="8" y="38" width="22" height="44" />
          <rect x="170" y="38" width="22" height="44" />
        </g>
      </svg>
    </div>
  );
}
