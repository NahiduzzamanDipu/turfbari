import { ChevronLeft, ChevronRight, Images, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { PublicPhoto } from "@/lib/types";
import { cn } from "@/lib/utils";

const PREVIEW = 8;

/** Thumbnail strip of the turf's photos; any photo opens a full-screen viewer (arrows / swipe / Esc). */
export function PhotoGallery({ photos, turfName }: { photos: PublicPhoto[]; turfName: string }) {
  const [open, setOpen] = useState<number | null>(null);
  if (photos.length === 0) return null;
  const shown = photos.slice(0, PREVIEW);
  const extra = photos.length - shown.length;

  return (
    <section aria-label="Photos">
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
        {shown.map((p, i) => {
          const isLast = i === shown.length - 1 && extra > 0;
          return (
            <button
              key={p.url}
              type="button"
              onClick={() => setOpen(i)}
              className="group relative aspect-[4/3] overflow-hidden rounded-lg bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50"
              aria-label={`Open photo ${i + 1} of ${photos.length}${p.caption ? `: ${p.caption}` : ""}`}
            >
              <img
                src={p.thumbnail_url}
                alt={p.caption || `${turfName} photo ${i + 1}`}
                loading="lazy"
                className="size-full object-cover transition duration-500 group-hover:scale-105"
              />
              {isLast && (
                <span className="absolute inset-0 flex items-center justify-center gap-2 bg-black/55 text-lg font-semibold text-white">
                  <Images className="size-5" /> +{extra}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {open !== null && <Lightbox photos={photos} start={open} turfName={turfName} onClose={() => setOpen(null)} />}
    </section>
  );
}

function Lightbox({
  photos,
  start,
  turfName,
  onClose,
}: {
  photos: PublicPhoto[];
  start: number;
  turfName: string;
  onClose: () => void;
}) {
  const [index, setIndex] = useState(start);
  const [touchX, setTouchX] = useState<number | null>(null);
  const go = useCallback((delta: number) => setIndex((i) => (i + delta + photos.length) % photos.length), [photos.length]);
  const photo = photos[index]!;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") go(1);
      if (e.key === "ArrowLeft") go(-1);
    };
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [go, onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`${turfName} photos`}
      className="fixed inset-0 z-[60] flex flex-col bg-black/95 text-white"
      onTouchStart={(e) => setTouchX(e.touches[0]?.clientX ?? null)}
      onTouchEnd={(e) => {
        const end = e.changedTouches[0]?.clientX;
        if (touchX !== null && end !== undefined && Math.abs(end - touchX) > 50) go(end < touchX ? 1 : -1);
        setTouchX(null);
      }}
    >
      <div className="flex items-center justify-between p-3 text-sm">
        <span className="tabular opacity-80">
          {index + 1} / {photos.length}
        </span>
        <button type="button" onClick={onClose} aria-label="Close photos" className="rounded-full p-2 hover:bg-white/10" autoFocus>
          <X className="size-6" />
        </button>
      </div>
      <div className="relative flex min-h-0 flex-1 items-center justify-center px-2 sm:px-16">
        <img
          key={photo.url}
          src={photo.url}
          alt={photo.caption || `${turfName} photo ${index + 1}`}
          className="max-h-full max-w-full rounded-md object-contain"
        />
        {photos.length > 1 && (
          <>
            <button
              type="button"
              aria-label="Previous photo"
              onClick={() => go(-1)}
              className="absolute left-2 top-1/2 hidden -translate-y-1/2 rounded-full bg-white/10 p-3 hover:bg-white/20 sm:block"
            >
              <ChevronLeft className="size-6" />
            </button>
            <button
              type="button"
              aria-label="Next photo"
              onClick={() => go(1)}
              className="absolute right-2 top-1/2 hidden -translate-y-1/2 rounded-full bg-white/10 p-3 hover:bg-white/20 sm:block"
            >
              <ChevronRight className="size-6" />
            </button>
          </>
        )}
      </div>
      <p className="min-h-12 p-3 text-center text-sm opacity-90">{photo.caption}</p>
      {photos.length > 1 && (
        <div className="flex justify-center gap-2 overflow-x-auto px-3 pb-4">
          {photos.map((p, i) => (
            <button
              key={p.url}
              type="button"
              aria-label={`Show photo ${i + 1}`}
              onClick={() => setIndex(i)}
              className={cn("size-14 shrink-0 overflow-hidden rounded-md border-2 transition", i === index ? "border-white" : "border-transparent opacity-60 hover:opacity-100")}
            >
              <img src={p.thumbnail_url} alt="" className="size-full object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
