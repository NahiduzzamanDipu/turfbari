import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface PublicYoutubeVideo {
  video_id: string | null;
  url: string | null;
  title: string;
  enabled: boolean;
}

/** One source of truth for the homepage intro and every turf's booking guide. */
export function usePublicYoutubeVideo(scope: "homepage" | "booking") {
  return useQuery({
    queryKey: ["public", "youtube", scope],
    queryFn: () => api<PublicYoutubeVideo>(scope === "homepage" ? "/public/youtube/homepage/" : "/public/youtube/"),
    // Revalidate on page navigation/focus so admin video updates show up consistently.
    staleTime: 0,
  });
}
