import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { RouterProvider } from "react-router";
import { Toaster } from "sonner";
import { ApiError } from "@/lib/api";
import { router } from "./router";

export function makeQueryClient() {
  const client: QueryClient = new QueryClient({
    // After any successful change (booking, payment, edit…), refetch every loaded screen so nothing
    // needs a manual reload. Changes made on other devices arrive through useLiveSync.
    mutationCache: new MutationCache({
      onSuccess: () => client.invalidateQueries(),
    }),
    defaultOptions: {
      queries: {
        staleTime: 5_000,
        refetchOnWindowFocus: true,
        // Don't retry client errors (4xx) — they won't fix themselves.
        retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
      },
    },
  });
  return client;
}

export function App() {
  const [queryClient] = useState(makeQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <Toaster richColors position="top-center" />
    </QueryClientProvider>
  );
}
