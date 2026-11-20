import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { RouterProvider } from "react-router";
import { Toaster } from "sonner";
import { ApiError } from "@/lib/api";
import { router } from "./router";

// The server answers 403 legal_acceptance_required when updated terms must be accepted first:
// refresh "me" so the route guard sends the user to the acceptance screen.
const onApiError = (client: QueryClient) => (error: Error) => {
  if (error instanceof ApiError && error.code === "legal_acceptance_required") {
    void client.invalidateQueries({ queryKey: ["auth", "me"] });
  }
};

export function makeQueryClient() {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: (e) => onApiError(client)(e) }),
    // After any successful change (booking, payment, edit…), refetch every loaded screen so nothing
    // needs a manual reload. Changes made on other devices arrive through useLiveSync.
    mutationCache: new MutationCache({
      onSuccess: () => client.invalidateQueries(),
      onError: (e) => onApiError(client)(e),
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
