import { useMutation } from "@tanstack/react-query";
import { Eye, EyeOff, KeyRound, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FormField, Input } from "@/components/ui/form";
import { errorText } from "@/features/workspace/hooks";
import { api } from "@/lib/api";
import { useMe } from "./auth";
import { TwoFactorCard } from "./TwoFactorCard";

const EMPTY = { current_password: "", new_password: "", confirm: "" };

/** "My account" for every signed-in user — Super Admin, owners and managers. */
export function AccountPage() {
  const me = useMe();
  const user = me.data?.user;
  const [pw, setPw] = useState(EMPTY);
  const [show, setShow] = useState(false);
  const mismatch = pw.confirm !== "" && pw.confirm !== pw.new_password;

  const change = useMutation({
    mutationFn: () =>
      api<void>("/auth/change-password/", {
        method: "POST",
        json: { current_password: pw.current_password, new_password: pw.new_password, new_password_confirm: pw.confirm },
      }),
    onSuccess: () => {
      toast.success("Password changed. Use the new password next time you sign in.");
      setPw(EMPTY);
    },
  });

  const role = user?.is_platform_admin
    ? "Super Admin"
    : (me.data?.memberships.find((m) => m.turf_id === me.data?.active_turf_id)?.role ?? "");

  return (
    <>
      <PageHeader title="My account" description="Your sign-in details and password." />
      <div className="grid max-w-3xl gap-6 md:grid-cols-[1fr_1.3fr]">
        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            <div>
              <p className="text-muted-foreground">Name</p>
              <p className="font-medium">{user?.full_name || "—"}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Email (used to sign in)</p>
              <p className="break-all font-medium">{user?.email}</p>
            </div>
            {user?.phone && (
              <div>
                <p className="text-muted-foreground">Phone</p>
                <p className="font-medium">{user.phone}</p>
              </div>
            )}
            {role && (
              <div>
                <p className="text-muted-foreground">Role</p>
                <p className="font-medium capitalize">{role}</p>
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="size-4" /> Change password
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="flex flex-col gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (!mismatch) change.mutate();
              }}
            >
              <FormField label="Current password">
                {(id) => (
                  <Input
                    id={id}
                    type={show ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    value={pw.current_password}
                    onChange={(e) => setPw({ ...pw, current_password: e.target.value })}
                  />
                )}
              </FormField>
              <FormField label="New password" hint="At least 10 characters. Avoid common words.">
                {(id) => (
                  <Input
                    id={id}
                    type={show ? "text" : "password"}
                    autoComplete="new-password"
                    minLength={10}
                    required
                    value={pw.new_password}
                    onChange={(e) => setPw({ ...pw, new_password: e.target.value })}
                  />
                )}
              </FormField>
              <FormField label="Confirm new password" error={mismatch ? "Passwords do not match." : undefined}>
                {(id) => (
                  <Input
                    id={id}
                    type={show ? "text" : "password"}
                    autoComplete="new-password"
                    required
                    value={pw.confirm}
                    onChange={(e) => setPw({ ...pw, confirm: e.target.value })}
                  />
                )}
              </FormField>
              <button
                type="button"
                className="flex items-center gap-1.5 self-start text-xs text-muted-foreground hover:text-foreground"
                onClick={() => setShow((s) => !s)}
              >
                {show ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                {show ? "Hide passwords" : "Show passwords"}
              </button>
              {change.error && <p className="text-sm text-destructive">{errorText(change.error)}</p>}
              <Button type="submit" disabled={change.isPending || mismatch} className="self-start">
                {change.isPending && <Loader2 className="animate-spin" />} Update password
              </Button>
            </form>
          </CardContent>
        </Card>
        {user?.is_platform_admin && <TwoFactorCard />}
      </div>
    </>
  );
}
