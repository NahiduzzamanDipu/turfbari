import { Link } from "react-router";
import { Logo } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center gap-6 px-4 text-center">
      <Logo />
      <div>
        <p className="font-display text-7xl font-extrabold text-primary">404</p>
        <h1 className="mt-2 text-xl font-semibold">This page is off the pitch</h1>
        <p className="mt-1 text-muted-foreground">The link may be wrong or the page may have moved.</p>
      </div>
      <Button asChild>
        <Link to="/">Back to TURFOS</Link>
      </Button>
    </main>
  );
}
