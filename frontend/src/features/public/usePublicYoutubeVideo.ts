import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface PublicYoutubeVideo {
  video_id: string | null;
}

/** One source of truth for the homepage intro and every turf's booking guide. */
export function usePublicYoutubeVideo() {
  return useQuery({
    queryKey: ["public", "youtube"],
    queryFn: () => api<PublicYoutubeVideo>("/public/youtube/"),
    // Revalidate on page navigation/focus so admin video updates show up consistently.
    staleTime: 0,
  });
}
