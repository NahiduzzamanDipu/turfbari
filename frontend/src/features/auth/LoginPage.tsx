import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, LogIn } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import { Logo } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox, FormField, Input } from "@/components/ui/form";
import { ApiError, api } from "@/lib/api";
import type { Me } from "@/lib/types";
import { meKey, useMe } from "./auth";

export function LoginPage() {
  const me = useMe();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);

  const login = useMutation({
    mutationFn: () => api<Me>("/auth/login/", { method: "POST", json: { identifier, password, remember } }),
    onSuccess: (data) => {
      qc.setQueryData(meKey, data);
      const next = params.get("next");
      // Only follow same-app relative paths.
      navigate(next?.startsWith("/") && !next.startsWith("//") ? next : data.home, { replace: true });
    },
  });

  if (me.data?.authenticated && !login.isPending && !login.isSuccess) {
    return <Navigate to={me.data.home} replace />;
  }

  const error = login.error instanceof ApiError ? login.error : null;

  return (
    <main className="relative flex min-h-dvh items-center justify-center overflow-hidden px-4 py-10">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(50rem_30rem_at_0%_0%,color-mix(in_oklch,var(--accent)_30%,transparent),transparent),radial-gradient(40rem_30rem_at_100%_100%,color-mix(in_oklch,var(--primary)_25%,transparent),transparent)]"
      />
      <div className="relative w-full max-w-sm">
        <Link to="/" className="mb-8 flex justify-center">
          <Logo />
        </Link>
        <Card>
          <CardContent className="flex flex-col gap-5">
            <div>
              <h1 className="text-xl font-semibold">Sign in</h1>
              <p className="text-sm text-muted-foreground">
                One login for turf owners, managers and TURFOS admins.
              </p>
            </div>
            <form
              className="flex flex-col gap-4"
              onSubmit={(e) => {
                e.preventDefault();
                login.mutate();
              }}
            >
              <FormField label="Email or username" error={error?.fields?.identifier}>
                {(id) => (
                  <Input
                    id={id}
                    autoComplete="username"
                    required
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                  />
                )}
              </FormField>
              <FormField label="Password" error={error?.fields?.password}>
                {(id) => (
                  <Input
                    id={id}
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                )}
              </FormField>
              <Checkbox
                label="Keep me signed in"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
              />
              {login.error && !error?.fields && (
                <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {login.error.message}
                </p>
              )}
              <Button type="submit" disabled={login.isPending}>
                {login.isPending ? <Loader2 className="animate-spin" /> : <LogIn />}
                Sign in
              </Button>
            </form>
          </CardContent>
        </Card>
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Own a turf?{" "}
          <Link to="/register-turf" className="font-semibold text-primary hover:underline">
            List it on TURFOS
          </Link>
        </p>
      </div>
    </main>
  );
}
