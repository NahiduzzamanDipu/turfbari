import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, LogIn, ShieldCheck } from "lucide-react";
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
  const [needsCode, setNeedsCode] = useState(false);
  const [code, setCode] = useState("");
  const [challenge, setChallenge] = useState<Pick<Me, "two_factor_method" | "email_hint" | "can_use_authenticator">>(
    {},
  );

  const finish = (data: Me) => {
    qc.setQueryData(meKey, data);
    const next = params.get("next");
    // Only follow same-app relative paths.
    if (data.user?.must_change_password) {
      navigate("/set-password", { replace: true });
      return;
    }
    navigate(next?.startsWith("/") && !next.startsWith("//") ? next : data.home, { replace: true });
  };
  const login = useMutation({
    mutationFn: () => api<Me>("/auth/login/", { method: "POST", json: { identifier, password, remember } }),
    onSuccess: (data) => {
      if (data.two_factor_required) {
        setChallenge({
          two_factor_method: data.two_factor_method,
          email_hint: data.email_hint,
          can_use_authenticator: data.can_use_authenticator,
        });
        setNeedsCode(true);
        setPassword("");
        return;
      }
      finish(data);
    },
  });
  const verify = useMutation({
    mutationFn: () => api<Me>("/auth/2fa/verify/", { method: "POST", json: { code } }),
    onSuccess: finish,
    onError: (e) => {
      if (e instanceof ApiError && e.code === "two_factor_expired") {
        setNeedsCode(false);
        setCode("");
      }
    },
  });

  const resend = useMutation({
    mutationFn: () => api<{ sent: boolean; email_hint: string }>("/auth/2fa/resend/", { method: "POST" }),
    onError: (e) => {
      if (e instanceof ApiError && e.code === "two_factor_expired") {
        setNeedsCode(false);
        setCode("");
      }
    },
  });
  const byEmail = challenge.two_factor_method === "email";

  if (me.data?.authenticated && !login.isPending && !login.isSuccess && !verify.isSuccess) {
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
          {needsCode ? (
            <CardContent className="flex flex-col gap-5">
              <div>
                <h1 className="flex items-center gap-2 text-xl font-semibold">
                  <ShieldCheck className="size-5 text-primary" /> {byEmail ? "Check your email" : "Two-factor check"}
                </h1>
                <p className="text-sm text-muted-foreground">
                  {byEmail ? (
                    <>
                      We emailed a 6-digit sign-in code to <span className="font-medium">{challenge.email_hint}</span>.
                      It expires in 10 minutes.
                      {challenge.can_use_authenticator && " You can also use your authenticator app or a recovery code."}
                    </>
                  ) : (
                    "Enter the 6-digit code from your authenticator app, or one of your recovery codes."
                  )}
                </p>
              </div>
              <form
                className="flex flex-col gap-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  verify.mutate();
                }}
              >
                <FormField label="Code" error={verify.error instanceof ApiError ? verify.error.fields?.code : null}>
                  {(id) => (
                    <Input
                      id={id}
                      autoFocus
                      required
                      autoComplete="one-time-code"
                      inputMode="text"
                      placeholder="123456"
                      className="text-center font-mono text-lg tracking-[0.3em]"
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                    />
                  )}
                </FormField>
                {verify.error && !(verify.error instanceof ApiError && verify.error.fields) && (
                  <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    {verify.error.message}
                  </p>
                )}
                <Button type="submit" disabled={verify.isPending}>
                  {verify.isPending ? <Loader2 className="animate-spin" /> : <ShieldCheck />}
                  Verify and sign in
                </Button>
                {byEmail && (
                  <div className="text-center text-xs">
                    {resend.isSuccess ? (
                      <p className="text-primary">A new code is on its way.</p>
                    ) : (
                      <button
                        type="button"
                        className="font-medium text-primary hover:underline disabled:opacity-50"
                        disabled={resend.isPending}
                        onClick={() => resend.mutate()}
                      >
                        Didn't get it? Send a new code
                      </button>
                    )}
                    {resend.error && <p className="mt-1 text-destructive">{resend.error.message}</p>}
                  </div>
                )}
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => {
                    setNeedsCode(false);
                    setCode("");
                  }}
                >
                  Use a different account
                </button>
              </form>
            </CardContent>
          ) : (
          <CardContent className="flex flex-col gap-5">
            <div>
              <h1 className="text-xl font-semibold">Sign in</h1>
              <p className="text-sm text-muted-foreground">
                One login for turf owners and their managers.
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
              <div className="flex items-center justify-between gap-2">
                <Checkbox
                  label="Keep me signed in"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                />
                <Link to="/forgot-password" className="text-sm font-medium text-primary hover:underline">
                  Forgot password?
                </Link>
              </div>
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
          )}
        </Card>
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Own a turf?{" "}
          <Link to="/register-turf" className="font-semibold text-primary hover:underline">
            Register it on TurfBari
          </Link>
        </p>
      </div>
    </main>
  );
}
