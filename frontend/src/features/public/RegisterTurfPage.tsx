import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Loader2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FormField, Input, Select, Textarea } from "@/components/ui/form";
import { ApiError, api } from "@/lib/api";
import { useLocations } from "./shared";

const EMPTY = {
  turf_name: "",
  owner_name: "",
  phone: "",
  email: "",
  district: "",
  area: "",
  address: "",
  turf_type: "outdoor",
  number_of_fields: "1",
  message: "",
  website: "",
};

export function RegisterTurfPage() {
  const locations = useLocations();
  const [form, setForm] = useState(EMPTY);
  const set = (key: keyof typeof EMPTY) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value, ...(key === "district" ? { area: "" } : {}) }));

  const submit = useMutation({
    mutationFn: () =>
      api<{ detail: string }>("/public/applications/", {
        method: "POST",
        json: { ...form, area: form.area || null, number_of_fields: Number(form.number_of_fields) },
      }),
  });
  const errors = submit.error instanceof ApiError ? submit.error.fields : null;
  const districts = (locations.data ?? []).flatMap((d) => d.districts).sort((a, b) => a.name.localeCompare(b.name));
  const areas = districts.find((d) => d.slug === form.district)?.areas ?? [];

  return (
    <div className="mx-auto grid max-w-6xl gap-10 px-4 py-10 lg:grid-cols-[1fr_32rem]">
      <div>
        <h1 className="font-display text-5xl font-extrabold uppercase leading-none">List your turf on TurfBari</h1>
        <p className="mt-4 text-lg text-muted-foreground">
          Tell us about your turf. After a quick call we set up your workspace and send your login.
        </p>
        <ol className="mt-8 flex flex-col gap-4">
          {[
            ["Apply", "Fill in this form — it takes two minutes."],
            ["We verify", "Our team calls you to confirm the details."],
            ["Go live", "Get your owner login, set prices and start taking bookings."],
          ].map(([title, text], i) => (
            <li key={title} className="flex gap-4">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent font-bold text-accent-foreground">
                {i + 1}
              </span>
              <div>
                <p className="font-semibold">{title}</p>
                <p className="text-sm text-muted-foreground">{text}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>

      <Card>
        <CardContent>
          {submit.isSuccess ? (
            <div className="flex flex-col items-center gap-3 py-8 text-center" role="status">
              <CheckCircle2 className="size-12 text-primary" />
              <p className="text-lg font-semibold">Application received</p>
              <p className="text-muted-foreground">{submit.data.detail}</p>
              <Button asChild variant="outline" className="mt-2">
                <Link to="/">Back to home</Link>
              </Button>
            </div>
          ) : (
            <form
              className="flex flex-col gap-4"
              onSubmit={(e) => {
                e.preventDefault();
                submit.mutate();
              }}
            >
              <FormField label="Turf name" error={errors?.turf_name}>
                {(id) => <Input id={id} required value={form.turf_name} onChange={set("turf_name")} />}
              </FormField>
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField label="Your name" error={errors?.owner_name}>
                  {(id) => <Input id={id} required autoComplete="name" value={form.owner_name} onChange={set("owner_name")} />}
                </FormField>
                <FormField label="Mobile number" error={errors?.phone}>
                  {(id) => <Input id={id} required type="tel" placeholder="01XXXXXXXXX" value={form.phone} onChange={set("phone")} />}
                </FormField>
              </div>
              <FormField label="Email" error={errors?.email} hint="Your owner login will use this email.">
                {(id) => <Input id={id} required type="email" autoComplete="email" value={form.email} onChange={set("email")} />}
              </FormField>
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField label="District" error={errors?.district}>
                  {(id) => (
                    <Select id={id} required value={form.district} onChange={set("district")}>
                      <option value="">Choose…</option>
                      {districts.map((d) => (
                        <option key={d.slug} value={d.slug}>
                          {d.name}
                        </option>
                      ))}
                    </Select>
                  )}
                </FormField>
                <FormField label="Area (optional)" error={errors?.area}>
                  {(id) => (
                    <Select id={id} value={form.area} onChange={set("area")} disabled={areas.length === 0}>
                      <option value="">{areas.length ? "Choose…" : "—"}</option>
                      {areas.map((a) => (
                        <option key={a.slug} value={a.slug}>
                          {a.name}
                        </option>
                      ))}
                    </Select>
                  )}
                </FormField>
              </div>
              <FormField label="Address" error={errors?.address}>
                {(id) => <Input id={id} required value={form.address} onChange={set("address")} />}
              </FormField>
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField label="Type" error={errors?.turf_type}>
                  {(id) => (
                    <Select id={id} value={form.turf_type} onChange={set("turf_type")}>
                      <option value="outdoor">Outdoor</option>
                      <option value="indoor">Indoor</option>
                      <option value="rooftop">Rooftop</option>
                    </Select>
                  )}
                </FormField>
                <FormField label="Number of fields" error={errors?.number_of_fields}>
                  {(id) => <Input id={id} type="number" min={1} max={20} required value={form.number_of_fields} onChange={set("number_of_fields")} />}
                </FormField>
              </div>
              <FormField label="Anything else? (optional)">
                {(id) => <Textarea id={id} rows={3} value={form.message} onChange={set("message")} />}
              </FormField>
              <input type="text" tabIndex={-1} autoComplete="off" aria-hidden className="hidden" value={form.website} onChange={set("website")} />
              {submit.error && !errors && (
                <p role="alert" className="text-sm text-destructive">
                  {submit.error.message}
                </p>
              )}
              <Button type="submit" size="lg" disabled={submit.isPending}>
                {submit.isPending && <Loader2 className="animate-spin" />}
                Submit application
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
