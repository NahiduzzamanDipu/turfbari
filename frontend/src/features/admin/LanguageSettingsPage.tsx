import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Globe2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Select } from "@/components/ui/form";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";

type Settings = { default_language: "en" | "bn"; new_account_language: "en" | "bn"; visitors_can_switch: boolean; available_languages: ("en" | "bn")[] };

export function AdminLanguageSettingsPage() {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["admin", "language-settings"], queryFn: () => api<Settings>("/admin/language-settings/") });
  const [form, setForm] = useState<Settings>({ default_language: "en", new_account_language: "en", visitors_can_switch: true, available_languages: ["en", "bn"] });
  useEffect(() => { if (query.data) setForm(query.data); }, [query.data]);
  const save = useMutation({
    mutationFn: () => api<Settings>("/admin/language-settings/", { method: "PUT", json: form }),
    onSuccess: (data) => { setForm(data); qc.setQueryData(["admin", "language-settings"], data); qc.invalidateQueries({ queryKey: ["public", "language-settings"] }); toast.success(t("Language settings saved.")); },
  });
  if (query.isLoading) return <p role="status">{t("Loading")}</p>;
  return <div className="space-y-6">
    <PageHeader title="Language settings" description="Set platform defaults. A user's explicit preference is preserved." />
    <Card className="max-w-2xl">
      <CardHeader><CardTitle className="flex items-center gap-2"><Globe2 className="size-5" /> Language preferences</CardTitle></CardHeader>
      <CardContent className="space-y-5">
        <label className="block space-y-2 text-sm font-medium">{t("Default platform language")}
          <Select value={form.default_language} onChange={(e) => setForm({ ...form, default_language: e.target.value as Settings["default_language"] })}>
            <option value="en">English</option><option value="bn">বাংলা</option>
          </Select>
        </label>
        <label className="block space-y-2 text-sm font-medium">{t("Default language for new accounts")}
          <Select value={form.new_account_language} onChange={(e) => setForm({ ...form, new_account_language: e.target.value as Settings["new_account_language"] })}>
            <option value="en">English</option><option value="bn">বাংলা</option>
          </Select>
        </label>
        <Checkbox label={t("Allow visitors to switch languages")} checked={form.visitors_can_switch} onChange={(event) => setForm({ ...form, visitors_can_switch: event.target.checked })} />
        <p className="text-sm text-muted-foreground">Both supported languages remain enabled: বাংলা and English. This setting does not override a user's saved language.</p>
        <Button onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? t("Loading") : t("Save")}</Button>
      </CardContent>
    </Card>
  </div>;
}
