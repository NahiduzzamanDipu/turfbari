import {
  BarChart3,
  CalendarCheck2,
  CalendarClock,
  Mail,
  MessageSquareText,
  MapPin,
  Phone,
  Share2,
  QrCode,
  ShieldCheck,
  Smartphone,
  Tags,
  Users,
  Wallet,
} from "lucide-react";
import { Link } from "react-router";
import type React from "react";
import { Button } from "@/components/ui/button";
import { useMe } from "@/features/auth/auth";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

/**
 * TurfBari's own site is about the product for turf owners. There is no public directory of turfs:
 * players reach a turf through that turf's own link or QR code (/turfs/<slug>).
 */
const FEATURES = [
  { icon: <QrCode />, title: "Your own booking page", text: "Every turf gets its own link and QR code. Players scan, pick a slot and book — no app, no account." },
  { icon: <Wallet />, title: "bKash advance, verified by you", text: "Players send the advance by bKash and submit the transaction ID. You approve or reject it in one tap." },
  { icon: <ShieldCheck />, title: "No double bookings", text: "A slot is held while a player pays and locked once you approve, so two teams never get the same hour." },
  { icon: <MessageSquareText />, title: "SMS confirmations", text: "Players get a Bengali SMS when you confirm, and owners get reminders before the plan ends." },
  { icon: <Tags />, title: "Morning to midnight pricing", text: "Set Morning, Evening, Night and Midnight prices, special-date rates and your own slot times." },
  { icon: <BarChart3 />, title: "Money and reports", text: "Advances, dues, expenses and monthly revenue from your real bookings, exportable to Excel." },
];

const STEPS = [
  { icon: <Smartphone />, title: "Player opens your page", text: "From your QR code at the counter, Facebook or a shared link." },
  { icon: <CalendarClock />, title: "Picks a slot and pays", text: "Sends the advance to your bKash number and submits the transaction ID." },
  { icon: <CalendarCheck2 />, title: "You approve, they get an SMS", text: "Check your bKash, tap Approve — the booking is confirmed." },
];

export function HomePage() {
  const me = useMe();
  const contact = useQuery({
    queryKey: ["public", "contact"],
    queryFn: () => api<ContactDetails>("/public/contact/"),
    staleTime: 5 * 60_000,
  });
  const signedIn = me.data?.authenticated;

  return (
    <>
      <section className="relative overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(60rem_30rem_at_10%_-10%,color-mix(in_oklch,var(--accent)_40%,transparent),transparent),radial-gradient(50rem_30rem_at_110%_10%,color-mix(in_oklch,var(--primary)_28%,transparent),transparent)]"
        />
        <div className="relative mx-auto max-w-6xl px-4 pb-16 pt-14 sm:pt-24">
          <p className="mb-3 inline-flex rounded-full bg-accent px-3 py-1 text-xs font-bold uppercase tracking-wider text-accent-foreground">
            টার্ফ ম্যানেজমেন্ট সফটওয়্যার · For turf owners in Bangladesh
          </p>
          <h1 className="max-w-3xl font-display text-5xl font-extrabold uppercase leading-[0.95] tracking-tight sm:text-7xl">
            Run your turf. Not a notebook.
          </h1>
          <p className="mt-4 max-w-xl text-lg text-muted-foreground">
            Bookings, bKash advances, slot pricing, managers, SMS and reports — in one workspace, with your own booking
            page and QR code for players.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            {signedIn ? (
              <Button asChild size="lg">
                <Link to={me.data?.home ?? "/"}>Open my dashboard</Link>
              </Button>
            ) : (
              <>
                <Button asChild size="lg">
                  <Link to="/register-turf">Register your turf</Link>
                </Button>
                <Button asChild size="lg" variant="outline">
                  <Link to="/login">Sign in</Link>
                </Button>
              </>
            )}
          </div>
          <p className="mt-6 text-sm text-muted-foreground">
            Booked a slot already?{" "}
            <Link to="/booking-status" className="font-semibold text-primary hover:underline">
              Check your booking status
            </Link>
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12" aria-labelledby="features">
        <h2 id="features" className="mb-6 font-display text-3xl font-extrabold uppercase">
          Everything a turf needs
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="glass rounded-xl p-5">
              <div className="mb-3 inline-flex rounded-lg bg-accent p-2 text-accent-foreground [&_svg]:size-5">{f.icon}</div>
              <h3 className="font-semibold">{f.title}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12" aria-labelledby="how">
        <h2 id="how" className="mb-6 font-display text-3xl font-extrabold uppercase">
          How a booking works
        </h2>
        <ol className="grid gap-4 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <li key={s.title} className="rounded-xl border p-5">
              <div className="mb-3 flex items-center gap-3">
                <span className="tabular flex size-8 items-center justify-center rounded-full bg-primary font-bold text-primary-foreground">
                  {i + 1}
                </span>
                <span className="text-primary [&_svg]:size-5">{s.icon}</span>
              </div>
              <h3 className="font-semibold">{s.title}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-16">
        <div className="overflow-hidden rounded-2xl bg-primary p-8 text-primary-foreground sm:p-12">
          <div className="grid items-center gap-8 md:grid-cols-[1fr_auto]">
            <div>
              <h2 className="font-display text-4xl font-extrabold uppercase">Owners and managers, one workspace</h2>
              <p className="mt-3 max-w-xl opacity-90">
                Give managers exactly the access they need — taking bookings, verifying payments, managing slots — while
                billing and settings stay with you.
              </p>
              <ul className="mt-4 flex flex-wrap gap-4 text-sm opacity-90">
                <li className="flex items-center gap-1.5">
                  <Users className="size-4" /> Role-based access
                </li>
                <li className="flex items-center gap-1.5">
                  <ShieldCheck className="size-4" /> Audit log of every change
                </li>
              </ul>
            </div>
            <Button asChild variant="accent" size="lg">
              <Link to="/register-turf">Get started</Link>
            </Button>
          </div>
        </div>
      </section>
      {contact.data?.enabled && (
        <section id="contact" className="scroll-mt-24 border-t bg-muted/30" aria-labelledby="contact-heading">
          <div className="mx-auto max-w-6xl px-4 py-14 sm:py-16">
            <div className="mx-auto mb-8 max-w-2xl text-center">
              <p className="text-sm font-bold uppercase tracking-wider text-primary">Let's Talk</p>
              <h2 id="contact-heading" className="mt-2 font-display text-3xl font-extrabold uppercase sm:text-4xl">
                {contact.data.heading || "Get in Touch"}
              </h2>
              <p className="mt-3 text-muted-foreground">
                {contact.data.description || "Have questions about TURFBARI or want to bring your turf business online? We're here to help."}
              </p>
            </div>
            {contact.data.phone || contact.data.email || contact.data.facebook_url || contact.data.whatsapp || contact.data.address ? (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {contact.data.phone && <ContactCard icon={<Phone />} title="Phone" href={`tel:${contact.data.phone.replace(/[^+\d]/g, "")}`} value={contact.data.phone} />}
                {contact.data.email && <ContactCard icon={<Mail />} title="Email" href={`mailto:${contact.data.email}`} value={contact.data.email} />}
                {contact.data.facebook_url && <ContactCard icon={<Share2 />} title="Facebook" href={contact.data.facebook_url} value="Visit Facebook Page" external />}
                {contact.data.whatsapp && <ContactCard icon={<MessageSquareText />} title="WhatsApp" href={`https://wa.me/${contact.data.whatsapp.replace(/\D/g, "")}`} value={contact.data.whatsapp} external />}
                {contact.data.address && <div className="glass flex min-h-28 items-start gap-4 rounded-xl p-5"><span className="rounded-lg bg-accent p-3 text-accent-foreground"><MapPin aria-hidden="true" /></span><div><h3 className="font-semibold">Office</h3><p className="mt-1 text-sm text-muted-foreground">{contact.data.address}</p></div></div>}
              </div>
            ) : (
              <p className="rounded-xl border border-dashed bg-card px-5 py-8 text-center text-sm text-muted-foreground">
                Our contact details are being updated. Please check back soon.
              </p>
            )}
          </div>
        </section>
      )}
    </>
  );
}

interface ContactDetails {
  enabled: boolean;
  heading: string;
  description: string;
  phone: string | null;
  email: string | null;
  facebook_url: string | null;
  whatsapp: string | null;
  address: string | null;
}

function ContactCard({ icon, title, href, value, external = false }: {
  icon: React.ReactNode; title: string; href: string; value: string; external?: boolean;
}) {
  return (
    <a href={href} {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      aria-label={`${title}: ${value}`} className="glass group flex min-h-28 items-center gap-4 rounded-xl p-5 transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <span aria-hidden="true" className="rounded-lg bg-accent p-3 text-accent-foreground transition group-hover:bg-primary group-hover:text-primary-foreground">{icon}</span>
      <span className="min-w-0"><span className="block font-semibold">{title}</span><span className="mt-1 block break-words text-sm text-muted-foreground">{value}</span></span>
    </a>
  );
}
