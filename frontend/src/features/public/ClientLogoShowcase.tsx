import { useEffect, useRef, useState, type CSSProperties } from "react";

export interface ClientShowcaseClient {
  slug: string;
  name: string;
  logo_url: string;
  display_order: number;
}

export function ClientLogoShowcase({
  clients,
  heading,
  subtitle,
}: {
  clients: ClientShowcaseClient[];
  heading: string;
  subtitle: string;
}) {
  const [failedSlugs, setFailedSlugs] = useState<Set<string>>(() => new Set());
  const [copies, setCopies] = useState(2);
  const viewportRef = useRef<HTMLDivElement>(null);
  const sequenceRef = useRef<HTMLDivElement>(null);
  const visibleClients = clients.filter((client) => !failedSlugs.has(`${client.slug}:${client.logo_url}`));
  useEffect(() => {
    const viewport = viewportRef.current;
    const sequence = sequenceRef.current;
    if (!viewport || !sequence) return;
    const updateCopies = () => {
      const viewportWidth = viewport.clientWidth;
      const sequenceWidth = sequence.getBoundingClientRect().width;
      if (viewportWidth > 0 && sequenceWidth > 0) {
        setCopies(Math.max(2, Math.ceil(viewportWidth / sequenceWidth) + 1));
      }
    };
    updateCopies();
    window.addEventListener("resize", updateCopies);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updateCopies);
    observer?.observe(viewport);
    observer?.observe(sequence);
    return () => {
      window.removeEventListener("resize", updateCopies);
      observer?.disconnect();
    };
  }, [visibleClients.length]);
  if (!visibleClients.length) return null;
  const style = { "--client-count": visibleClients.length, "--client-copies": copies } as CSSProperties;

  return <section id="client-showcase" className="overflow-hidden border-y bg-muted/30 py-12 sm:py-16" aria-label={heading}>
    <div className="mx-auto max-w-6xl px-4 text-center">
      <h2 className="font-display text-3xl font-extrabold uppercase sm:text-4xl">{heading}</h2>
      {subtitle && <p className="mt-2 text-muted-foreground">{subtitle}</p>}
    </div>
    <div ref={viewportRef} className="client-logo-viewport mt-8" aria-label={heading}>
      <div className="client-logo-track" style={style}>
        {Array.from({ length: copies }, (_, copy) => <div
          key={copy}
          ref={copy === 0 ? sequenceRef : undefined}
          className={`client-logo-group${copy > 0 ? " client-logo-group-duplicate" : ""}`}
          aria-hidden={copy > 0 ? "true" : undefined}
          inert={copy > 0}
        >{visibleClients.map((client) => <ClientLogo key={client.slug} client={client} onError={() => setFailedSlugs((previous) => new Set(previous).add(`${client.slug}:${client.logo_url}`))} />)}</div>)}
      </div>
    </div>
  </section>;
}

function ClientLogo({ client, onError }: { client: ClientShowcaseClient; onError: () => void }) {
  return <div className="client-logo-item" title={client.name}>
    <div className="client-logo-frame">
      <img src={client.logo_url} alt={`${client.name} logo`} loading="lazy" decoding="async" onError={onError} />
    </div>
    <p className="mt-3 line-clamp-2 text-sm font-semibold">{client.name}</p>
  </div>;
}
