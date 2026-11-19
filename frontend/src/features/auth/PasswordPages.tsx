import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, KeyRound, Loader2, LogOut } from "lucide-react";
import { useState } from "react";
import { Link, Navigate } from "react-router";
import { Logo } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FormField, Input } from "@/components/ui/form";
import { ApiError, api } from "@/lib/api";
import { FullPageSpinner, meKey, useLogout, useMe } from "./auth";

function AuthShell({ children }: { children: React.ReactNode }) {
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
          <CardContent className="flex flex-col gap-5">{children}</CardContent>
        </Card>
      </div>
    </main>
  );
}

function Alert({ children }: { children: React.ReactNode }) {
  return (
    <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {children}
    </p>
  );
}

/** Strength hints that match the server rules (10+ characters, not common, not only numbers). */
function passwordProblems(value: string): string | null {
  if (!value) return null;
  if (value.length < 10) return `${10 - value.length} more character${value.length === 9 ? "" : "s"} needed`;
  if (/^\d+$/.test(value)) return "Add letters — numbers alone are too easy to guess";
  return null;
}

/** First sign-in on a temporary password: nothing else in the app opens until this is done. */
export function SetPasswordPage() {
  const me = useMe();
  const qc = useQueryClient();
  const logout = useLogout();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const save = useMutation({
    mutationFn: () => api<void>("/auth/change-password/", { method: "POST", json: { current_password: current, new_password: next } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: meKey }),
  });

  if (me.isPending) return <FullPageSpinner />;
  if (!me.data?.authenticated) return <Navigate to="/login" replace />;
  if (!me.data.user?.must_change_password) return <Navigate to={me.data.home} replace />;

  const fields = save.error instanceof ApiError ? save.error.fields : null;
  const mismatch = confirm.length > 0 && confirm !== next;
  const hint = passwordProblems(next);

  return (
    <AuthShell>
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <KeyRound className="size-5 text-primary" /> Set your own password
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          You signed in with a temporary password. Choose a new one to open your dashboard — the temporary password
          stops working once you do.
        </p>
      </div>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!mismatch && !hint) save.mutate();
        }}
      >
        <FormField label="Temporary password" error={fields?.current_password}>
          {(id) => <Input id={id} type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />}
        </FormField>
        <FormField label="New password" hint={hint ?? "At least 10 characters"} error={fields?.new_password}>
          {(id) => <Input id={id} type="password" autoComplete="new-password" required value={next} onChange={(e) => setNext(e.target.value)} />}
        </FormField>
        <FormField label="Repeat new password" error={mismatch ? ["The two passwords don't match."] : null}>
          {(id) => <Input id={id} type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />}
        </FormField>
        {save.error && !fields && <Alert>{save.error.message}</Alert>}
        <Button type="submit" disabled={save.isPending || mismatch || !!hint || !confirm}>
          {save.isPending ? <Loader2 className="animate-spin" /> : <CheckCircle2 />} Save and continue
        </Button>
        <button
          type="button"
          className="inline-flex items-center justify-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          onClick={() => logout.mutate()}
        >
          <LogOut className="size-3" /> Sign out
        </button>
      </form>
    </AuthShell>
  );
}

/** "Forgot password": request a 6-digit code by SMS/email, then set a new password with it. */
export function ForgotPasswordPage() {
  const [identifier, setIdentifier] = useState("");
  const [code, setCode] = useState("");
  const [next, setNext] = useState("");
  const [step, setStep] = useState<"ask" | "code" | "done">("ask");
  const request = useMutation({
    mutationFn: () => api<{ detail: string }>("/auth/password-reset/", { method: "POST", json: { identifier } }),
    onSuccess: () => setStep("code"),
  });
  const confirm = useMutation({
    mutationFn: () =>
      api<{ detail: string }>("/auth/password-reset/confirm/", { method: "POST", json: { identifier, code, new_password: next } }),
    onSuccess: () => setStep("done"),
  });
  const fields = confirm.error instanceof ApiError ? confirm.error.fields : null;
  const hint = passwordProblems(next);

  if (step === "done") {
    return (
      <AuthShell>
        <div className="text-center">
          <CheckCircle2 className="mx-auto size-10 text-primary" />
          <h1 className="mt-3 text-xl font-semibold">Password changed</h1>
          <p className="mt-1 text-sm text-muted-foreground">You've been signed out on every device. Sign in with your new password.</p>
        </div>
        <Button asChild>
          <Link to="/login">Go to sign in</Link>
        </Button>
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <div>
        <h1 className="text-xl font-semibold">Forgot your password?</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {step === "ask"
            ? "Enter your email, username or mobile number. We'll send a 6-digit code to the phone (SMS) or email on your account."
            : request.data?.detail}
        </p>
      </div>
      {step === "ask" ? (
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            request.mutate();
          }}
        >
          <FormField label="Email, username or mobile">
            {(id) => <Input id={id} autoComplete="username" required value={identifier} onChange={(e) => setIdentifier(e.target.value)} />}
          </FormField>
          {request.error && <Alert>{request.error.message}</Alert>}
          <Button type="submit" disabled={request.isPending}>
            {request.isPending && <Loader2 className="animate-spin" />} Send code
          </Button>
        </form>
      ) : (
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!hint) confirm.mutate();
          }}
        >
          <FormField label="6-digit code" error={fields?.code}>
            {(id) => (
              <Input
                id={id}
                required
                autoComplete="one-time-code"
                inputMode="numeric"
                maxLength={6}
                placeholder="123456"
                className="text-center font-mono text-lg tracking-[0.3em]"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              />
            )}
          </FormField>
          <FormField label="New password" hint={hint ?? "At least 10 characters"} error={fields?.new_password}>
            {(id) => <Input id={id} type="password" autoComplete="new-password" required value={next} onChange={(e) => setNext(e.target.value)} />}
          </FormField>
          {confirm.error && !fields && <Alert>{confirm.error.message}</Alert>}
          <Button type="submit" disabled={confirm.isPending || code.length !== 6 || !!hint}>
            {confirm.isPending && <Loader2 className="animate-spin" />} Change password
          </Button>
          <button
            type="button"
            className="text-xs text-muted-foreground hover:text-foreground"
            onClick={() => {
              setStep("ask");
              setCode("");
              request.reset();
              confirm.reset();
            }}
          >
            Didn't get a code? Try again
          </button>
        </form>
      )}
      <Link to="/login" className="text-center text-xs text-muted-foreground hover:text-foreground">
        Back to sign in
      </Link>
    </AuthShell>
  );
}
