import { Dialog } from "@/components/ui/form";

const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/;

/** The YouTube "play" mark (red rounded rectangle, white triangle). */
export function YouTubeIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 28 20" className={className} aria-hidden>
      <rect width="28" height="20" rx="5" fill="#FF0000" />
      <path d="M11.2 5.8v8.4l7.3-4.2-7.3-4.2Z" fill="#fff" />
    </svg>
  );
}

/**
 * Plays a YouTube video in a popup from youtube-nocookie.com. Only a validated 11-character ID ever
 * reaches the URL (never a pasted link). Nothing autoplays; closing unmounts the iframe, which stops it.
 */
export function YouTubeDialog({ videoId, title, onClose }: { videoId: string; title: string; onClose: () => void }) {
  const safeId = VIDEO_ID.test(videoId) ? videoId : null;
  return (
    <Dialog open onClose={onClose} title={title} wide>
      {safeId ? (
        <div className="aspect-video w-full overflow-hidden rounded-lg bg-black">
          <iframe
            className="size-full"
            src={`https://www.youtube-nocookie.com/embed/${safeId}?rel=0&modestbranding=1`}
            title={title}
            loading="lazy"
            allow="accelerometer; encrypted-media; gyroscope; picture-in-picture; fullscreen"
            referrerPolicy="strict-origin-when-cross-origin"
            allowFullScreen
          />
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">This video can't be played.</p>
      )}
    </Dialog>
  );
}
