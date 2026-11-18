import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Crosshair, Loader2, LocateFixed, SearchX, SlidersHorizontal, X } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Checkbox, EmptyState, ErrorState, Input, Label, Select } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { Paginated, TurfCard } from "@/lib/types";
import { cn } from "@/lib/utils";
import { TurfCardView, useAmenities, useLocations, usePlayerLocation } from "./shared";

const PAGE_SIZE = 12;

export function ExplorePage() {
  const [params, setParams] = useSearchParams();
  const [showFilters, setShowFilters] = useState(false);
  const locations = useLocations();
  const amenities = useAmenities();
  const page = Number(params.get("page") ?? "1");
  const { geo, locate, clear } = usePlayerLocation();
  const near = geo.status === "ready";

  const query = new URLSearchParams(params);
  query.set("page_size", String(PAGE_SIZE));
  if (near) {
    query.set("lat", String(geo.lat));
    query.set("lng", String(geo.lng));
  } else if (query.get("sort") === "nearest") {
    query.delete("sort");
  }
  const turfs = useQuery({
    queryKey: ["public", "turfs", query.toString()],
    queryFn: () => api<Paginated<TurfCard>>(`/public/turfs/?${query}`),
    placeholderData: keepPreviousData,
  });

  const update = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    if (key === "district") next.delete("area");
    setParams(next, { replace: true });
  };

  const districts = (locations.data ?? []).flatMap((d) => d.districts).sort((a, b) => a.name.localeCompare(b.name));
  const areas = districts.find((d) => d.slug === params.get("district"))?.areas ?? [];
  const selectedAmenities = params.getAll("amenity");
  const totalPages = turfs.data ? Math.max(1, Math.ceil(turfs.data.count / PAGE_SIZE)) : 1;

  const filters = (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="f-district">District</Label>
        <Select id="f-district" value={params.get("district") ?? ""} onChange={(e) => update("district", e.target.value)}>
          <option value="">All districts</option>
          {districts.map((d) => (
            <option key={d.slug} value={d.slug}>
              {d.name}
            </option>
          ))}
        </Select>
      </div>
      {areas.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="f-area">Area</Label>
          <Select id="f-area" value={params.get("area") ?? ""} onChange={(e) => update("area", e.target.value)}>
            <option value="">All areas</option>
            {areas.map((a) => (
              <option key={a.slug} value={a.slug}>
                {a.name}
              </option>
            ))}
          </Select>
        </div>
      )}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="f-type">Type</Label>
        <Select id="f-type" value={params.get("type") ?? ""} onChange={(e) => update("type", e.target.value)}>
          <option value="">Any</option>
          <option value="outdoor">Outdoor</option>
          <option value="indoor">Indoor</option>
          <option value="rooftop">Rooftop</option>
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="f-price">Max price per hour (৳)</Label>
        <Input
          id="f-price"
          type="number"
          min={0}
          step={100}
          placeholder="Any"
          defaultValue={params.get("max_price") ?? ""}
          onBlur={(e) => update("max_price", e.target.value)}
        />
      </div>
      <Checkbox
        label="Takes online requests"
        checked={params.get("bookable") === "1"}
        onChange={(e) => update("bookable", e.target.checked ? "1" : null)}
      />
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">Amenities</legend>
        {amenities.data?.map((a) => (
          <Checkbox
            key={a.slug}
            label={a.name}
            checked={selectedAmenities.includes(a.slug)}
            onChange={(e) => {
              const next = new URLSearchParams(params);
              next.delete("amenity");
              const values = e.target.checked
                ? [...selectedAmenities, a.slug]
                : selectedAmenities.filter((s) => s !== a.slug);
              for (const v of values) next.append("amenity", v);
              next.delete("page");
              setParams(next, { replace: true });
            }}
          />
        ))}
      </fieldset>
      <Button variant="ghost" size="sm" onClick={() => setParams({}, { replace: true })}>
        Clear filters
      </Button>
    </div>
  );

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="font-display text-4xl font-extrabold uppercase">Explore turfs</h1>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <form
          className="flex flex-1 gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            update("q", new FormData(e.currentTarget).get("q")?.toString().trim() || null);
          }}
        >
          <label htmlFor="explore-q" className="sr-only">
            Search
          </label>
          <Input id="explore-q" name="q" placeholder="Search by name, area or address" defaultValue={params.get("q") ?? ""} />
          <Button type="submit">Search</Button>
        </form>
        <div className="flex gap-2">
          <label htmlFor="sort" className="sr-only">
            Sort
          </label>
          <Select
            id="sort"
            value={params.get("sort") ?? (near ? "nearest" : "featured")}
            onChange={(e) => update("sort", e.target.value)}
          >
            {near && <option value="nearest">Nearest first</option>}
            <option value="featured">Featured first</option>
            <option value="price_asc">Price: low to high</option>
            <option value="price_desc">Price: high to low</option>
            <option value="newest">Newest</option>
            <option value="name">Name A–Z</option>
          </Select>
          <Button variant="outline" className="md:hidden" onClick={() => setShowFilters((v) => !v)} aria-expanded={showFilters}>
            <SlidersHorizontal /> Filters
          </Button>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm" aria-live="polite">
        {geo.status === "locating" && (
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Finding turfs near you...
          </span>
        )}
        {near && (
          <>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 font-medium text-primary">
              <LocateFixed className="size-4" /> Showing turfs nearest to you
            </span>
            <Button variant="ghost" size="sm" onClick={clear}>
              <X /> Stop using my location
            </Button>
          </>
        )}
        {(geo.status === "idle" || geo.status === "denied") && (
          <>
            <Button variant="outline" size="sm" onClick={locate}>
              <Crosshair /> Find turfs near me
            </Button>
            {geo.status === "denied" && (
              <span className="text-xs text-muted-foreground">
                Location is blocked. Allow it in your browser site settings, then try again.
              </span>
            )}
          </>
        )}
      </div>

      <div className="mt-4 grid gap-6 md:grid-cols-[14rem_1fr]">
        <aside className={cn("glass h-fit rounded-xl p-4 md:block", showFilters ? "block" : "hidden")}>{filters}</aside>
        <section aria-live="polite">
          {turfs.data && (
            <p className="mb-3 text-sm text-muted-foreground">
              {turfs.data.count} turf{turfs.data.count === 1 ? "" : "s"} found
            </p>
          )}
          {turfs.isError && <ErrorState error={turfs.error} onRetry={() => turfs.refetch()} />}
          <div className={cn("grid gap-4 sm:grid-cols-2 lg:grid-cols-3", turfs.isFetching && "opacity-70")}>
            {turfs.isPending && Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-72 rounded-xl" />)}
            {turfs.data?.results.map((t) => <TurfCardView key={t.slug} turf={t} />)}
          </div>
          {turfs.data?.count === 0 && (
            <EmptyState icon={<SearchX />} title="No turfs match these filters">
              Try a nearby district or remove a filter.
            </EmptyState>
          )}
          {totalPages > 1 && (
            <nav className="mt-6 flex items-center justify-center gap-3" aria-label="Pagination">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => update("page", String(page - 1))}>
                Previous
              </Button>
              <span className="text-sm">
                Page {page} of {totalPages}
              </span>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => update("page", String(page + 1))}>
                Next
              </Button>
            </nav>
          )}
        </section>
      </div>
    </div>
  );
}
