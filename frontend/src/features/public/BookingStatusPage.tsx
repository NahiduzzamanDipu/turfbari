import { useMutation } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge, FormField, Input, STATUS_TONE } from "@/components/ui/form";
import { api } from "@/lib/api";
import { fmtDay, fmtRange } from "@/lib/format";
import type { PublicBooking } from "@/lib/types";
import { formatBDT } from "@/lib/utils";

export function BookingStatusPage() {
  const [params] = useSearchParams();
  const [reference, setReference] = useState(params.get("reference") ?? "");
  const [phone, setPhone] = useState("");
  const lookup = useMutation({
    mutationFn: () =>
      api<PublicBooking>(
        `/public/bookings/lookup/?${new URLSearchParams({ reference: reference.trim(), phone: phone.trim() })}`,
      ),
  });

  return (
    <div className="mx-auto max-w-lg px-4 py-12">
      <h1 className="font-display text-4xl font-extrabold uppercase">Check your booking</h1>
      <p className="mt-2 text-muted-foreground">Enter the reference you received and the phone number you used.</p>
      <Card className="mt-6">
        <CardContent>
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              lookup.mutate();
            }}
          >
            <FormField label="Booking reference">
              {(id) => (
                <Input id={id} required placeholder="TRF-2611-ABCDE" className="font-mono uppercase" value={reference} onChange={(e) => setReference(e.target.value)} />
              )}
            </FormField>
            <FormField label="Mobile number">
              {(id) => <Input id={id} required type="tel" placeholder="01XXXXXXXXX" value={phone} onChange={(e) => setPhone(e.target.value)} />}
            </FormField>
            <Button type="submit" disabled={lookup.isPending}>
              {lookup.isPending ? <Loader2 className="animate-spin" /> : <Search />} Check status
            </Button>
          </form>
          {lookup.error && (
            <p role="alert" className="mt-4 text-sm text-destructive">
              {lookup.error.message}
            </p>
          )}
          {lookup.data && (
            <div className="mt-6 flex flex-col gap-2 border-t pt-4" role="status">
              <div className="flex items-center justify-between">
                <span className="font-mono font-bold">{lookup.data.reference}</span>
                <Badge tone={STATUS_TONE[lookup.data.status]}>{lookup.data.status_label}</Badge>
              </div>
              <p className="font-semibold">
                {lookup.data.turf} · {lookup.data.field}
              </p>
              <p className="text-sm text-muted-foreground">
                {fmtDay(lookup.data.start)}, {fmtRange(lookup.data.start, lookup.data.end)}
              </p>
              {lookup.data.total && <p className="tabular text-sm">Total: {formatBDT(lookup.data.total)}</p>}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
