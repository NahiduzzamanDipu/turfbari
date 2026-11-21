import {
  ArrowRight as ArrowRightIcon,
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
  CirclePlay,
  CheckCircle2,
  Star,
  Headphones,
  Play,
} from "lucide-react";
import { Link } from "react-router";
import { useState } from "react";
import type React from "react";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import { YouTubeDialog } from "@/components/content/YouTube";
import { useMe } from "@/features/auth/auth";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatBDT } from "@/lib/utils";
import { usePublicYoutubeVideo } from "./usePublicYoutubeVideo";
import { ClientLogoShowcase } from "./ClientLogoShowcase";

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
  const [aboutOpen, setAboutOpen] = useState(false);
  const { language: faqLanguage, t } = useLanguage();
  const me = useMe();
  const contact = useQuery({
    queryKey: ["public", "contact"],
    queryFn: () => api<ContactDetails>("/public/contact/"),
    staleTime: 5 * 60_000,
  });
  const signedIn = me.data?.authenticated;
  const plans = useQuery({ queryKey: ["public", "plans"], queryFn: () => api<PublicPlan[]>("/public/plans/"), staleTime: 5 * 60_000 });
  const smsPrice = useQuery({ queryKey: ["public", "sms-pricing"], queryFn: () => api<SmsPrice>("/public/sms-pricing/"), staleTime: 5 * 60_000 });
  const youtube = usePublicYoutubeVideo("homepage");
  const faqs = useQuery({ queryKey: ["public", "faqs"], queryFn: () => api<HomepageFAQ[]>("/public/faqs/"), staleTime: 5 * 60_000 });
  const showcase = useQuery({ queryKey: ["public", "client-showcase"], queryFn: () => api<ClientShowcaseData>("/public/client-showcase/"), staleTime: 30_000 });

  return (
    <>
      <section className="relative overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(60rem_30rem_at_10%_-10%,color-mix(in_oklch,var(--accent)_40%,transparent),transparent),radial-gradient(50rem_30rem_at_110%_10%,color-mix(in_oklch,var(--primary)_28%,transparent),transparent)]"
        />
        <div className="relative mx-auto max-w-6xl px-4 pb-12 pt-10 sm:pb-16 sm:pt-24">
          <p className="mb-3 inline-flex rounded-full bg-accent px-3 py-1 text-xs font-bold uppercase tracking-wider text-accent-foreground">
            টার্ফ ম্যানেজমেন্ট সফটওয়্যার · For turf owners in Bangladesh
          </p>
          <h1 className="max-w-3xl font-display text-4xl font-extrabold uppercase leading-[1.05] tracking-tight sm:text-7xl">
            {t("Run your turf. Not a notebook.")}
          </h1>
          <p className="mt-3 max-w-xl text-base text-muted-foreground sm:mt-4 sm:text-lg">
            Bookings, bKash advances, slot pricing, managers, SMS and reports — in one workspace, with your own booking
            page and QR code for players.
          </p>
          <div className="mt-6 flex flex-wrap gap-2.5 sm:mt-8 sm:gap-3">
            {signedIn ? (
              <Button asChild size="lg">
                <Link to={me.data?.home ?? "/"}>{t("Open my dashboard")}</Link>
              </Button>
            ) : (
              <>
                <Button asChild size="lg">
              <Link to="/register-turf">{t("Register your turf")}</Link>
                </Button>
                <Button asChild size="lg" variant="outline">
              <Link to="/login">{t("Sign in")}</Link>
                </Button>
              </>
            )}
            {youtube.data?.enabled && youtube.data.video_id && (
              <Button type="button" variant="outline" size="lg" onClick={() => setAboutOpen(true)}>
                <CirclePlay aria-hidden="true" className="text-red-600" /> {youtube.data.title || "About Us"}
              </Button>
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

      <section className="mx-auto max-w-6xl px-4 pb-8 sm:pb-12" aria-labelledby="demo-title">
        <div className="overflow-hidden rounded-2xl border bg-card shadow-sm">
          <div className="grid gap-4 bg-primary px-4 py-5 text-primary-foreground sm:gap-5 sm:px-8 sm:py-9 lg:grid-cols-[1fr_auto] lg:items-center">
            <div>
              <p className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-[.16em] text-primary-foreground/75"><Play className="size-4" /> {t("Try it before you decide")}</p>
              <h2 id="demo-title" className="mt-2 font-display text-2xl font-extrabold uppercase sm:text-4xl">{t("Try the live demo")}</h2>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-primary-foreground/85">Experience TURFBARI from both sides. See how customers book a turf and how owners manage their business. Demo data is isolated and temporary.</p>
            </div>
            <Button asChild variant="accent" size="lg"><Link to="/demo-booking">Try Live Demo <ArrowRightIcon /></Link></Button>
          </div>
          <div className="flex flex-col gap-3 border-t p-4 sm:flex-row sm:items-center sm:justify-between sm:px-8 sm:py-5">
            <p className="max-w-3xl text-sm text-muted-foreground">Start as a customer, submit a simulated booking, then open the connected Demo Owner Dashboard to review it. The two views share one isolated demo workspace.</p>
            <Button asChild variant="outline"><Link to="/demo-booking">Explore connected demo <ArrowRightIcon /></Link></Button>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-8 sm:py-12" aria-labelledby="features">
        <p className="mb-2 text-sm font-bold uppercase tracking-wider text-primary">{t("Built for day-to-day operations")}</p>
        <h2 id="features" className="mb-2 font-display text-2xl font-extrabold uppercase sm:mb-3 sm:text-3xl">Why Choose TURFBARI?</h2>
        <p className="mb-4 text-sm text-muted-foreground sm:mb-6 sm:text-base">Everything your turf business needs, organized in one simple platform.</p>
        <div className="grid gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="glass rounded-xl p-4 sm:p-5">
              <div className="mb-2 inline-flex rounded-lg bg-accent p-2 text-accent-foreground [&_svg]:size-5 sm:mb-3">{f.icon}</div>
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

      <section id="plans" className="scroll-mt-24 border-y bg-muted/30" aria-labelledby="plans-title">
        <div className="mx-auto max-w-6xl px-4 py-10 sm:py-14">
          <div className="mx-auto mb-8 max-w-2xl text-center">
            <p className="text-sm font-bold uppercase tracking-wider text-primary">Simple prepaid subscriptions</p>
            <h2 id="plans-title" className="mt-2 font-display text-2xl font-extrabold uppercase sm:text-3xl">Choose the Right Plan for Your Turf</h2>
            <p className="mt-3 text-muted-foreground">Flexible plans designed to help turf businesses manage bookings, customers, payments, and daily operations.</p>
          </div>
          {plans.isPending ? <p className="text-center text-sm text-muted-foreground" role="status">Loading available plans…</p> : plans.data?.length ? (
            <div className="grid items-stretch gap-4 md:grid-cols-2 lg:grid-cols-3">
              {plans.data.map((p) => <article key={p.id} className={`relative flex flex-col rounded-2xl border bg-card p-4 shadow-sm sm:p-6 ${p.featured ? "border-primary ring-2 ring-primary/20" : ""}`}>
                {p.featured && <span className="absolute -top-3 right-5 inline-flex items-center gap-1 rounded-full bg-primary px-3 py-1 text-xs font-bold text-primary-foreground"><Star className="size-3" /> Featured</span>}
                <h3 className="font-display text-2xl font-extrabold">{p.name}</h3>
                <p className="mt-1 min-h-10 text-sm text-muted-foreground">{p.description || `${p.months} month prepaid period`}</p>
                <p className="mt-5 text-3xl font-extrabold tabular">{formatBDT(p.price)}<span className="ml-2 text-sm font-medium text-muted-foreground">/ {p.months} month{p.months === 1 ? "" : "s"}</span></p>
                <ul className="my-5 flex-1 space-y-2 text-sm">
                  {p.features.map((feature) => <li key={feature} className="flex gap-2"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary" />{feature}</li>)}
                  <li className="flex gap-2"><CheckCircle2 className={`mt-0.5 size-4 shrink-0 ${p.sms_enabled ? "text-primary" : "text-muted-foreground"}`} />SMS {p.sms_enabled ? "available with prepaid wallet" : "not included"}</li>
                  {Object.entries(p.limits).filter(([, v]) => v !== null && v !== "" && v !== false).map(([label, value]) => <li key={label} className="flex gap-2"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary" /><span className="capitalize">{label.replaceAll("_", " ")}: {String(value)}</span></li>)}
                  {!p.features.length && !Object.keys(p.limits).length && <li className="text-muted-foreground">Plan details are available from TURFBARI support.</li>}
                </ul>
                <Button asChild className="w-full"><Link to={signedIn ? "/workspace/subscription" : `/register-turf?plan=${encodeURIComponent(p.period)}`}>{signedIn ? "Request this plan" : "Choose Plan"}</Link></Button>
              </article>)}
            </div>
          ) : <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">There are no public plans available right now. Please contact TURFBARI for plan information.</p>}
          {plans.isError && <p role="alert" className="mt-3 text-center text-sm text-destructive">Couldn’t load plans. Please try again later.</p>}
          <p className="mt-5 text-center text-xs text-muted-foreground">Subscriptions are prepaid. They do not renew automatically; plan changes require TURFBARI approval.</p>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-4 px-4 py-10 sm:gap-6 sm:py-14 md:grid-cols-2" aria-labelledby="sms-price-title">
        <div className="rounded-2xl bg-primary p-5 text-primary-foreground sm:p-9">
          <p className="inline-flex items-center gap-2 text-sm font-semibold"><MessageSquareText className="size-4" /> Prepaid messaging</p>
          <h2 id="sms-price-title" className="mt-3 font-display text-2xl font-extrabold uppercase sm:text-3xl">Affordable SMS Communication</h2>
          {smsPrice.data?.configured && smsPrice.data.price_per_segment ? <>
            <p className="mt-5 text-4xl font-extrabold tabular">{formatBDT(smsPrice.data.price_per_segment)} <span className="text-base font-medium">per SMS part</span></p>
            <p className="mt-2 text-sm text-primary-foreground/80">Booking confirmations, customer updates, reminders and promotional messages use your prepaid SMS wallet. Recharge before sending.</p>
            <div className="mt-5 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">{smsPrice.data.examples.map((row) => <div key={row.segments} className="rounded-lg bg-white/10 px-3 py-2">{row.segments} part{row.segments > 1 ? "s" : ""}<span className="float-right font-semibold">{formatBDT(row.cost)}</span></div>)}</div>
            <p className="mt-3 text-xs text-primary-foreground/75">Bengali and longer messages may use multiple parts depending on encoding and length. The final segment count and charge are shown before sending. Messages are not sent when wallet balance is insufficient; bookings continue normally.</p>
          </> : <p className="mt-4 text-sm text-primary-foreground/85">SMS service pricing is being configured. Contact TURFBARI for current rates. Messages use a prepaid wallet, and the applicable cost is shown before sending.</p>}
        </div>
        <div className="rounded-2xl border bg-card p-5 sm:p-9">
          <div className="inline-flex rounded-lg bg-accent p-2 text-accent-foreground"><Headphones className="size-5" /></div>
          <h2 className="mt-3 font-display text-2xl font-extrabold uppercase sm:text-3xl">Support &amp; Personal Training</h2>
          <p className="mt-3 text-muted-foreground">After your subscription is activated, TURFBARI support staff can guide you through the workspace and its day-to-day tools. Availability and response times can vary.</p>
          <ol className="mt-5 space-y-2 text-sm text-muted-foreground">
            {["Choose a plan and submit your registration payment for verification.", "Once approved, your account is activated.", "Arrange an onboarding session with the support team.", "Learn profile setup, slots and pricing, bookings, payment verification, QR sharing, SMS wallet, staff and reports.", "Contact support again when you need help."].map((step, i) => <li key={step} className="flex gap-3"><span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-bold text-accent-foreground">{i + 1}</span>{step}</li>)}
          </ol>
          <div className="mt-6 flex flex-wrap gap-3">{contact.data?.enabled && <Button asChild><a href="#contact">Contact Support</a></Button>}<Button asChild variant="outline"><Link to="/register-turf">Get Started</Link></Button></div>
        </div>
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
      {showcase.data?.enabled && showcase.data.clients.length > 0 && <ClientLogoShowcase
        clients={showcase.data.clients}
        heading={faqLanguage === "bn" ? showcase.data.heading_bn : showcase.data.heading_en}
        subtitle={faqLanguage === "bn" ? showcase.data.subtitle_bn : showcase.data.subtitle_en}
      />}
      {faqs.data?.length ? <FAQSection faqs={faqs.data} language={faqLanguage} t={t} /> : null}
      {aboutOpen && youtube.data?.enabled && youtube.data.video_id && (
        <YouTubeDialog videoId={youtube.data.video_id} title={youtube.data.title || "About Us"} onClose={() => setAboutOpen(false)} />
      )}
    </>
  );
}

function FAQSection({ faqs, language, t }: { faqs: HomepageFAQ[]; language: string; t: (key: string) => string }) {
  const [expanded, setExpanded] = useState(false);
  const hasMore = faqs.length > 4;
  const visibleFaqs = expanded ? faqs : faqs.slice(0, 4);

  return <section className="mx-auto max-w-4xl px-4 py-14" aria-labelledby="faq-title">
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3"><div><p className="text-sm font-bold uppercase tracking-wider text-primary">{t("Helpful answers")}</p><h2 id="faq-title" className="mt-2 font-display text-3xl font-extrabold uppercase">{t("Frequently Asked Questions")}</h2></div></div>
    <div className="space-y-3">
      {visibleFaqs.slice(0, 4).map((faq) => <FAQItem key={faq.id} faq={faq} language={language} />)}
      {hasMore && <div id="faq-extra" className={`grid transition-[grid-template-rows,opacity] duration-300 ease-out motion-reduce:transition-none ${expanded ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"}`} aria-hidden={!expanded} inert={!expanded}>
        <div className="min-h-0 overflow-hidden space-y-3">{visibleFaqs.slice(4).map((faq) => <FAQItem key={faq.id} faq={faq} language={language} />)}</div>
      </div>}
    </div>
    {hasMore && <div className="mt-5 flex justify-center"><Button type="button" variant="outline" aria-expanded={expanded} aria-controls="faq-extra" onClick={() => setExpanded((value) => !value)}>{t(expanded ? "See Less" : "See More")}</Button></div>}
  </section>;
}

function FAQItem({ faq, language }: { faq: HomepageFAQ; language: string }) {
  return <details className="group rounded-xl border bg-card px-5 py-4">
    <summary className="cursor-pointer list-none pr-7 font-semibold marker:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring after:ml-2 after:text-primary after:content-['+']">{language === "bn" && faq.question_bn ? faq.question_bn : faq.question_en}</summary>
    <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-muted-foreground">{language === "bn" && faq.answer_bn ? faq.answer_bn : faq.answer_en}</p>
  </details>;
}
interface PublicPlan { id: string; period: string; name: string; months: number; price: string; description: string; featured: boolean; features: string[]; limits: Record<string, string | number | boolean | null>; sms_enabled: boolean }
interface SmsPrice { configured: boolean; price_per_segment: string | null; examples: { segments: number; cost: string }[] }
interface HomepageFAQ { id: string; question_en: string; answer_en: string; question_bn: string; answer_bn: string }
interface ClientShowcaseData {
  enabled: boolean;
  heading_en: string;
  heading_bn: string;
  subtitle_en: string;
  subtitle_bn: string;
  clients: { slug: string; name: string; logo_url: string; display_order: number }[];
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
