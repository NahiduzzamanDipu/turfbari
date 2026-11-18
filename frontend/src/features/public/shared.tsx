import { useQuery } from "@tanstack/react-query";
import { Building2, MapPin, Navigation, Sun } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
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

export type GeoState =
  | { status: "idle" | "locating" | "denied" | "unsupported" }
  | { status: "ready"; lat: number; lng: number };

const GEO_KEY = "turfbari:player-location";

function readCachedLocation(): GeoState | null {
  try {
    const raw = sessionStorage.getItem(GEO_KEY);
    if (!raw) return null;
    const { lat, lng } = JSON.parse(raw) as { lat: number; lng: number };
    return Number.isFinite(lat) && Number.isFinite(lng) ? { status: "ready", lat, lng } : null;
  } catch {
    return null;
  }
}

/**
 * The player's approximate position for "near me" search. Detected automatically on pages that use
 * it (the browser asks for permission once); kept only for this tab session and rounded to ~100 m.
 */
export function usePlayerLocation({ auto = true }: { auto?: boolean } = {}) {
  const [geo, setGeo] = useState<GeoState>(() => readCachedLocation() ?? { status: "idle" });

  const locate = useCallback(() => {
    if (!("geolocation" in navigator)) {
      setGeo({ status: "unsupported" });
      return;
    }
    setGeo({ status: "locating" });
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = Math.round(pos.coords.latitude * 1000) / 1000;
        const lng = Math.round(pos.coords.longitude * 1000) / 1000;
        try {
          sessionStorage.setItem(GEO_KEY, JSON.stringify({ lat, lng }));
        } catch {
          /* storage blocked: still works for this page */
        }
        setGeo({ status: "ready", lat, lng });
      },
      () => setGeo({ status: "denied" }),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 5 * 60_000 },
    );
  }, []);

  const clear = useCallback(() => {
    try {
      sessionStorage.removeItem(GEO_KEY);
    } catch {
      /* ignore */
    }
    setGeo({ status: "idle" });
  }, []);

  useEffect(() => {
    if (!auto || geo.status !== "idle") return;
    // Ask straight away unless the player already blocked location for this site.
    const perms = navigator.permissions?.query?.({ name: "geolocation" as PermissionName });
    if (!perms) {
      locate();
      return;
    }
    perms.then((p) => (p.state === "denied" ? setGeo({ status: "denied" }) : locate())).catch(locate);
  }, [auto]);

  return { geo, locate, clear };
}

/** Opens the turf on Google Maps. A button (not a link) because cards are already links. */
export function MapButton({ href }: { href: string }) {
  return (
    <button
      type="button"
      aria-label="Open location in Google Maps"
      title="Open in Google Maps"
      className="inline-flex size-9 items-center justify-center rounded-full bg-white/95 shadow transition hover:scale-110 hover:bg-white"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        window.open(href, "_blank", "noopener,noreferrer");
      }}
    >
      <GoogleMapsPin className="size-5" />
    </button>
  );
}

/** Map-pin glyph in map colours (generic pin shape, no logo). */
export function GoogleMapsPin({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path fill="#EA4335" d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7Z" />
      <circle cx="12" cy="9" r="2.6" fill="#fff" />
    </svg>
  );
}

export function formatDistance(km: number): string {
  if (km < 1) return `${Math.max(50, Math.round((km * 1000) / 50) * 50)} m away`;
  return `${km < 10 ? km.toFixed(1) : Math.round(km)} km away`;
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
        {turf.cover_url ? (
          <img
            src={turf.cover_url}
            alt=""
            loading="lazy"
            className="size-full object-cover transition duration-500 group-hover:scale-105"
          />
        ) : (
          <TurfArt seed={turf.slug} className="size-full transition duration-500 group-hover:scale-105" />
        )}
        <div className="absolute left-3 top-3 flex gap-1.5">
          {turf.is_featured && <Badge tone="lime">Featured</Badge>}
          <Badge className="bg-black/50 text-white">
            <TypeIcon className="size-3" />
            {TURF_TYPE_LABEL[turf.turf_type]}
          </Badge>
        </div>
        {turf.map_link && (
          <div className="absolute right-3 top-3">
            <MapButton href={turf.map_link} />
          </div>
        )}
        {turf.distance_km != null && (
          <Badge className="absolute bottom-3 left-3 bg-black/60 text-white">
            <Navigation className="size-3" />
            {formatDistance(turf.distance_km)}
          </Badge>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-center gap-2.5">
          {turf.profile_image_url && (
            <img
              src={turf.profile_image_url}
              alt=""
              loading="lazy"
              className="relative z-10 -mt-9 size-12 shrink-0 rounded-full border-[3px] border-card object-cover shadow"
            />
          )}
          <h3 className="font-semibold leading-tight">{turf.name}</h3>
        </div>
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
