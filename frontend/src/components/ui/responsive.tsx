import type * as React from "react";
import { cn } from "@/lib/utils";

export function ResponsiveDataTable({
  mobile,
  desktop,
  className,
}: {
  mobile: React.ReactNode;
  desktop: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="grid gap-3 md:hidden">{mobile}</div>
      <div className="hidden md:block">{desktop}</div>
    </div>
  );
}

export function MobileRecordCard({
  children,
  className,
}: React.ComponentProps<"div">) {
  return <div className={cn("rounded-xl border bg-card p-4 shadow-sm", className)}>{children}</div>;
}
