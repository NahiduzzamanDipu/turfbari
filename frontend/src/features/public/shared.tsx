import { useQuery } from "@tanstack/react-query";
import { Building2, MapPin, Sun } from "lucide-react";
import { Link } from "react-router";
import { Badge } from "@/components/ui/form";
import { api } from "@/lib/api";
import { TURF_TYPE_LABEL } from "@/lib/format";
import type { Division, TurfCard } from "@/lib/types";
import { formatBDT } from "@/lib/utils";

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

/** Deterministic pitch-pattern artwork per turf, so cards look distinct without uploaded photos. */
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

export function TurfCardView({ turf }: { turf: TurfCard }) {
  const TypeIcon = turf.turf_type === "indoor" ? Building2 : Sun;
  return (
    <Link
      to={`/turfs/${turf.slug}`}
      className="glass group flex flex-col overflow-hidden rounded-xl transition hover:-translate-y-0.5 hover:shadow-lg focus-visible:ring-[3px] focus-visible:ring-ring/50"
    >
      <div className="relative h-36 overflow-hidden">
        <TurfArt seed={turf.slug} className="size-full transition duration-500 group-hover:scale-105" />
        <div className="absolute left-3 top-3 flex gap-1.5">
          {turf.is_featured && <Badge tone="lime">Featured</Badge>}
          <Badge className="bg-black/50 text-white">
            <TypeIcon className="size-3" />
            {TURF_TYPE_LABEL[turf.turf_type]}
          </Badge>
        </div>
      </div>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <h3 className="font-semibold leading-tight">{turf.name}</h3>
        <p className="flex items-center gap-1 text-sm text-muted-foreground">
          <MapPin className="size-3.5 shrink-0" />
          {[turf.area?.name, turf.district.name].filter(Boolean).join(", ")}
        </p>
        {turf.short_description && (
          <p className="line-clamp-2 text-sm text-muted-foreground">{turf.short_description}</p>
        )}
        <div className="mt-auto flex items-end justify-between pt-2">
          <span className="text-xs text-muted-foreground">
            {turf.fields_count} field{turf.fields_count === 1 ? "" : "s"}
          </span>
          {turf.min_price ? (
            <span className="text-sm">
              from <span className="tabular font-bold text-primary">{formatBDT(turf.min_price)}</span>
              <span className="text-muted-foreground">/hr</span>
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">Call for price</span>
          )}
        </div>
      </div>
    </Link>
  );
}
