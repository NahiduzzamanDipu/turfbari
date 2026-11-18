import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Download, Loader2, ShieldCheck, ShieldOff } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, FormField, Input } from "@/components/ui/form";
import { errorText } from "@/features/workspace/hooks";
import { ApiError, api } from "@/lib/api";

interface Status {
  enabled: boolean;
  recovery_codes_left: number;
}
interface Setup {
  secret: string;
  otpauth_uri: string;
  qr_svg: string;
}

const KEY = ["auth", "2fa"];

function fieldError(e: unknown, name: string): string | undefined {
  return e instanceof ApiError ? e.fields?.[name]?.[0] : undefined;
}

/** Super Admin: turn on two-factor sign-in with an authenticator app (Google Authenticator, Authy…). */
export function TwoFactorCard() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: KEY, queryFn: () => api<Status>("/auth/2fa/") });
  const [setup, setSetup] = useState<Setup | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const done = (newCodes?: string[]) => {
    setCode("");
    setPassword("");
    if (newCodes) setCodes(newCodes);
    qc.invalidateQueries({ queryKey: KEY });
  };

  const start = useMutation({
    mutationFn: () => api<Setup>("/auth/2fa/setup/", { method: "POST" }),
    onSuccess: (s) => {
      setSetup(s);
      setCodes(null);
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const confirm = useMutation({
    mutationFn: () => api<{ recovery_codes: string[] }>("/auth/2fa/confirm/", { method: "POST", json: { code } }),
    onSuccess: (r) => {
      setSetup(null);
      toast.success("Two-factor sign-in is on");
      done(r.recovery_codes);
    },
  });
  const regenerate = useMutation({
    mutationFn: () => api<{ recovery_codes: string[] }>("/auth/2fa/recovery-codes/", { method: "POST", json: { code } }),
    onSuccess: (r) => {
      toast.success("New recovery codes created — the old ones no longer work");
      done(r.recovery_codes);
    },
  });
  const disable = useMutation({
    mutationFn: () => api("/auth/2fa/disable/", { method: "POST", json: { code, password } }),
    onSuccess: () => {
      toast.success("Two-factor sign-in is off");
      setCodes(null);
      done();
    },
  });

  const enabled = status.data?.enabled;
  const copyAll = () =>
    navigator.clipboard.writeText((codes ?? []).join("\n")).then(() => toast.success("Recovery codes copied"));
  const download = () => {
    const blob = new Blob([`TurfBari recovery codes\n\n${(codes ?? []).join("\n")}\n`], { type: "text/plain" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "turfbari-recovery-codes.txt" });
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <Card className="md:col-span-2">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-2">
          <span className="flex items-center gap-2">
            <ShieldCheck className="size-4" /> Two-factor sign-in
          </span>
          {status.data && <Badge tone={enabled ? "green" : "neutral"}>{enabled ? "On" : "Off"}</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        <p className="text-muted-foreground">
          After your password, sign-in also asks for a 6-digit code from an authenticator app on your phone (Google
          Authenticator, Microsoft Authenticator, Authy…). Someone who learns your password still can't get in.
        </p>

        {codes && (
          <div className="rounded-lg border border-amber-500/50 bg-amber-400/10 p-4">
            <p className="font-semibold">Save your recovery codes now</p>
            <p className="mb-3 text-xs text-muted-foreground">
              Each code works once if you lose your phone. They are shown only this time.
            </p>
            <ul className="mb-3 grid grid-cols-2 gap-x-6 gap-y-1 font-mono sm:grid-cols-5">
              {codes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={copyAll}>
                <Copy /> Copy
              </Button>
              <Button size="sm" variant="outline" onClick={download}>
                <Download /> Download
              </Button>
              <Button size="sm" onClick={() => setCodes(null)}>
                I've saved them
              </Button>
            </div>
          </div>
        )}

        {!enabled && !setup && (
          <Button className="self-start" onClick={() => start.mutate()} disabled={start.isPending || status.isPending}>
            {start.isPending ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Turn on two-factor sign-in
          </Button>
        )}

        {!enabled && setup && (
          <div className="grid gap-4 sm:grid-cols-[auto_1fr]">
            <img src={setup.qr_svg} alt="QR code to add TurfBari to your authenticator app" className="size-44 rounded-lg bg-white p-1" />
            <form
              className="flex flex-col gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                confirm.mutate();
              }}
            >
              <ol className="list-decimal space-y-1 pl-5 text-muted-foreground">
                <li>Open your authenticator app and scan this QR code.</li>
                <li>
                  Can't scan? Enter this key: <code className="break-all rounded bg-secondary px-1 font-mono text-foreground">{setup.secret}</code>
                </li>
                <li>Type the 6-digit code the app shows.</li>
              </ol>
              <FormField label="6-digit code" error={fieldError(confirm.error, "code")}>
                {(id) => (
                  <Input id={id} required inputMode="numeric" autoComplete="one-time-code" maxLength={7} className="max-w-40 font-mono tracking-widest" value={code} onChange={(e) => setCode(e.target.value)} />
                )}
              </FormField>
              <div className="flex gap-2">
                <Button type="submit" disabled={confirm.isPending}>
                  {confirm.isPending && <Loader2 className="animate-spin" />} Confirm and turn on
                </Button>
                <Button type="button" variant="ghost" onClick={() => setSetup(null)}>
                  Cancel
                </Button>
              </div>
            </form>
          </div>
        )}

        {enabled && (
          <div className="flex flex-col gap-3">
            <p>
              Recovery codes left: <strong className="tabular">{status.data?.recovery_codes_left}</strong>
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField label="Current 6-digit code" hint="Needed to make new recovery codes or turn this off." error={fieldError(regenerate.error ?? disable.error, "code")}>
                {(id) => <Input id={id} inputMode="numeric" autoComplete="one-time-code" className="font-mono tracking-widest" value={code} onChange={(e) => setCode(e.target.value)} />}
              </FormField>
              <FormField label="Password (to turn off)" error={fieldError(disable.error, "password")}>
                {(id) => <Input id={id} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />}
              </FormField>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" disabled={!code || regenerate.isPending} onClick={() => regenerate.mutate()}>
                New recovery codes
              </Button>
              <Button variant="destructive" disabled={!code || !password || disable.isPending} onClick={() => disable.mutate()}>
                <ShieldOff /> Turn off
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
