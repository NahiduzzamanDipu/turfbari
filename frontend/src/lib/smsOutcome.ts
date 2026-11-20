import { toast } from "sonner";

export interface SmsOutcome {
  status: string;
  label: string;
  reason: string;
  block_reason: string | null;
  charged: string;
}

/** After a booking the turf made: tell the owner what happened to the customer's confirmation SMS. */
export function showSmsOutcome(sms: SmsOutcome | null | undefined) {
  if (!sms) return;
  if (sms.status === "sent" || sms.status === "queued" || sms.status === "sending") {
    toast.success("Confirmation SMS sent to the customer");
  } else if (sms.block_reason === "insufficient_balance") {
    toast.warning("Booking confirmed, but the SMS wasn't sent: not enough SMS Wallet balance. Recharge and retry it from SMS.", {
      duration: 10_000,
    });
  } else {
    toast.warning(`Booking confirmed, but the SMS wasn't sent: ${sms.reason || sms.label}`, { duration: 8_000 });
  }
}
