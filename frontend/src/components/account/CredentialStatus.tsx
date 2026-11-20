import { Clock, Loader2, MessageSquareText, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, type BadgeTone } from "@/components/ui/form";

/** Status of a temporary password sent by SMS. The password itself is never sent to the browser. */
export interface CredentialInfo {
  id: string;
  purpose: "account_created" | "admin_reset";
  channel: "sms" | "shown_once";
  status: "queued" | "retrying" | "submitted" | "failed" | "shown" | "used" | "superseded" | "expired";
  status_label: string;
  masked_phone: string;
  created_at: string;
  expires_at: string;
  submitted_at: string | null;
  sends: number;
  sms_status: string | null;
  sms_detail: string;
  delivery_reports: boolean;
  can_resend: boolean;
}

const TONE: Record<CredentialInfo["status"], BadgeTone> = {
  queued: "blue",
  retrying: "amber",
  submitted: "green",
  failed: "red",
  shown: "neutral",
  used: "green",
  superseded: "neutral",
  expired: "red",
};

const LABEL: Partial<Record<CredentialInfo["status"], string>> = {
  queued: "Queued",
  retrying: "Retrying",
  submitted: "Submitted",
  failed: "Failed",
  expired: "Expired",
  used: "Password changed",
};

const fmt = (iso: string | null) =>
  iso
    ? new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Dhaka", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }).format(new Date(iso))
    : "—";

export function CredentialStatus({
  credential,
  onResend,
  resending,
}: {
  credential: CredentialInfo;
  onResend?: () => void;
  resending?: boolean;
}) {
  const c = credential;
  const sms = c.channel === "sms";
  return (
    <div role="status" className="rounded-lg border bg-secondary/40 p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-medium">
          <MessageSquareText className="size-4 text-primary" />
          {c.purpose === "admin_reset" ? "Password reset" : "Login details"}
          {sms ? ` sent by SMS to ${c.masked_phone}` : " — shown once to the creator"}
        </p>
        <Badge tone={TONE[c.status]}>{LABEL[c.status] ?? c.status_label}</Badge>
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground sm:grid-cols-3">
        <div>
          <dt className="inline">Reset at </dt>
          <dd className="inline text-foreground">{fmt(c.created_at)}</dd>
        </div>
        <div>
          <dt className="inline">Expires </dt>
          <dd className="inline text-foreground">{fmt(c.expires_at)}</dd>
        </div>
        {sms && (
          <div>
            <dt className="inline">SMS sent </dt>
            <dd className="inline text-foreground">{c.sends}×</dd>
          </div>
        )}
      </dl>
      {c.status === "submitted" && (
        <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="size-3" /> The SMS provider accepted it. It gives no delivery report, so ask the person if it didn't arrive.
        </p>
      )}
      {(c.status === "failed" || c.status === "retrying") && c.sms_detail && <p className="mt-2 text-xs text-destructive">{c.sms_detail}</p>}
      {sms && c.can_resend && onResend && (
        <Button
          size="sm"
          variant="outline"
          className="mt-3"
          disabled={resending}
          onClick={() => {
            const note =
              c.status === "failed" || c.status === "queued" || c.status === "retrying"
                ? "Send the same temporary password again?"
                : "Its SMS was already handed over (or it expired), so a NEW temporary password will be made and the previous one stops working. Continue?";
            if (window.confirm(note)) onResend();
          }}
        >
          {resending ? <Loader2 className="animate-spin" /> : <RotateCcw />} Resend SMS
        </Button>
      )}
    </div>
  );
}
