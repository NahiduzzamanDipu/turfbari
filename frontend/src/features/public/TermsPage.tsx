import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FileText, ListChecks } from "lucide-react";
import { Link, useSearchParams } from "react-router";
import { FormattedText } from "@/components/content/FormattedText";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";

interface PublicTerms {
  id: number;
  version: number;
  terms_body: string;
  rules_body: string;
  published_at: string;
}

/** The platform-wide Terms & Conditions and Booking Rules every customer agrees to when booking. */
export function TermsPage() {
  const [params] = useSearchParams();
  const turf = params.get("turf");
  const terms = useQuery({ queryKey: ["public", "terms"], queryFn: () => api<PublicTerms>("/public/terms/"), retry: false });
  const missing = terms.error instanceof ApiError && terms.error.status === 404;

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      {turf && /^[a-z0-9-]+$/.test(turf) && (
        <Link to={`/turfs/${turf}`} className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> Back to booking
        </Link>
      )}
      <h1 className="font-display text-4xl font-extrabold uppercase">Terms &amp; Conditions</h1>
      <p className="mt-1 text-muted-foreground" lang="bn">
        শর্তাবলী ও বুকিং নিয়মাবলী — TurfBari-র সব টার্ফে প্রযোজ্য
      </p>
      {terms.isPending && <Skeleton className="mt-6 h-64" />}
      {missing && <p className="mt-6 text-muted-foreground">No terms have been published yet.</p>}
      {terms.isError && !missing && <ErrorState error={terms.error} onRetry={() => terms.refetch()} />}
      {terms.data && (
        <div className="mt-6 flex flex-col gap-6">
          <p className="text-xs text-muted-foreground">
            Version {terms.data.version} · published{" "}
            {new Date(terms.data.published_at).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}
          </p>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="size-5 text-primary" /> General Terms &amp; Conditions
              </CardTitle>
            </CardHeader>
            <CardContent>
              <FormattedText text={terms.data.terms_body} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ListChecks className="size-5 text-primary" /> Booking Rules &amp; Regulations
              </CardTitle>
            </CardHeader>
            <CardContent>
              <FormattedText text={terms.data.rules_body} />
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
