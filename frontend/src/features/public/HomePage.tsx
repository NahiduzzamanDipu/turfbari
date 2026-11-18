import { useQuery } from "@tanstack/react-query";
import { CalendarCheck2, QrCode, Search, ShieldCheck, Store, Timer } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { Paginated, TurfCard } from "@/lib/types";
import { TurfCardView, useLocations } from "./shared";

export function HomePage() {
  const navigate = useNavigate();
  const locations = useLocations();
  const [q, setQ] = useState("");
  const [district, setDistrict] = useState("");
  const featured = useQuery({
    queryKey: ["public", "turfs", "featured"],
    queryFn: () => api<Paginated<TurfCard>>("/public/turfs/?sort=featured&page_size=6"),
  });
  const stats = useQuery({
    queryKey: ["public", "stats"],
    queryFn: () => api<{ turfs: number; districts: number; fields: number }>("/public/stats/"),
  });
  const districts = (locations.data ?? []).flatMap((d) => d.districts).sort((a, b) => a.name.localeCompare(b.name));

  return (
    <>
      <section className="relative overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(60rem_30rem_at_10%_-10%,color-mix(in_oklch,var(--accent)_40%,transparent),transparent),radial-gradient(50rem_30rem_at_110%_10%,color-mix(in_oklch,var(--primary)_28%,transparent),transparent)]"
        />
        <div className="relative mx-auto max-w-6xl px-4 pb-16 pt-14 sm:pt-24">
          <p className="mb-3 inline-flex rounded-full bg-accent px-3 py-1 text-xs font-bold uppercase tracking-wider text-accent-foreground">
            Football turfs across Bangladesh
          </p>
          <h1 className="max-w-3xl font-display text-5xl font-extrabold uppercase leading-[0.95] tracking-tight sm:text-7xl">
            Find a turf. Book a slot. Play tonight.
          </h1>
          <p className="mt-4 max-w-xl text-lg text-muted-foreground">
            See real availability and prices, then send a booking request in under a minute. No account needed.
          </p>
          <form
            className="glass mt-8 flex max-w-2xl flex-col gap-2 rounded-xl p-2 sm:flex-row"
            onSubmit={(e) => {
              e.preventDefault();
              const params = new URLSearchParams();
              if (q.trim()) params.set("q", q.trim());
              if (district) params.set("district", district);
              navigate(`/explore?${params}`);
            }}
          >
            <label className="sr-only" htmlFor="home-q">
              Search turfs
            </label>
            <Input
              id="home-q"
              placeholder="Turf name or area, e.g. Mirpur"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="border-0 bg-transparent shadow-none"
            />
            <label className="sr-only" htmlFor="home-district">
              District
            </label>
            <Select
              id="home-district"
              value={district}
              onChange={(e) => setDistrict(e.target.value)}
              className="sm:max-w-48"
            >
              <option value="">All districts</option>
              {districts.map((d) => (
                <option key={d.slug} value={d.slug}>
                  {d.name}
                </option>
              ))}
            </Select>
            <Button type="submit" size="lg" className="h-10">
              <Search /> Search
            </Button>
          </form>
          {stats.data && stats.data.turfs > 0 && (
            <dl className="mt-8 flex gap-8 text-sm">
              {[
                ["Turfs listed", stats.data.turfs],
                ["Fields", stats.data.fields],
                ["Districts", stats.data.districts],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="tabular font-display text-3xl font-bold">{value}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12">
        <div className="mb-6 flex items-end justify-between">
          <h2 className="font-display text-3xl font-extrabold uppercase">Popular turfs</h2>
          <Link to="/explore" className="text-sm font-semibold text-primary hover:underline">
            See all
          </Link>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {featured.isPending &&
            Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-72 rounded-xl" />)}
          {featured.data?.results.map((t) => <TurfCardView key={t.slug} turf={t} />)}
        </div>
        {featured.data?.results.length === 0 && (
          <p className="text-muted-foreground">No turfs are listed yet. Check back soon.</p>
        )}
      </section>

      <section className="mx-auto grid max-w-6xl gap-4 px-4 py-12 md:grid-cols-3">
        {[
          { icon: <Search />, title: "Search by area", text: "Filter by district, area, indoor or outdoor, amenities and price." },
          { icon: <Timer />, title: "Live slot times", text: "See which hours are free today and the exact price for each slot." },
          { icon: <CalendarCheck2 />, title: "Request in a minute", text: "Send your name and phone. The turf confirms and you can track it." },
        ].map((f) => (
          <div key={f.title} className="glass rounded-xl p-5">
            <div className="mb-3 inline-flex rounded-lg bg-accent p-2 text-accent-foreground [&_svg]:size-5">
              {f.icon}
            </div>
            <h3 className="font-semibold">{f.title}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{f.text}</p>
          </div>
        ))}
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-16">
        <div className="overflow-hidden rounded-2xl bg-primary p-8 text-primary-foreground sm:p-12">
          <div className="grid items-center gap-8 md:grid-cols-[1fr_auto]">
            <div>
              <h2 className="font-display text-4xl font-extrabold uppercase">Run a turf? Go digital.</h2>
              <p className="mt-3 max-w-xl opacity-90">
                Bookings calendar, peak and weekend pricing, payments and dues, expenses, managers, reports and a
                QR code for your counter — all in one workspace.
              </p>
              <ul className="mt-4 flex flex-wrap gap-4 text-sm opacity-90">
                <li className="flex items-center gap-1.5"><ShieldCheck className="size-4" /> No double bookings</li>
                <li className="flex items-center gap-1.5"><QrCode className="size-4" /> QR booking page</li>
                <li className="flex items-center gap-1.5"><Store className="size-4" /> Public listing</li>
              </ul>
            </div>
            <Button asChild variant="accent" size="lg">
              <Link to="/register-turf">List your turf</Link>
            </Button>
          </div>
        </div>
      </section>
    </>
  );
}
