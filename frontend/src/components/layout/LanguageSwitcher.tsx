import { Languages } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";

export function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const { language, setLanguage, canSwitch, t } = useLanguage();
  if (!canSwitch) return null;
  return (
    <div className="inline-flex items-center gap-1 rounded-lg border bg-background p-1" role="group" aria-label={t("Choose a language")}>
      <Languages aria-hidden="true" className="ml-1 size-4 text-muted-foreground" />
      {(["bn", "en"] as const).map((value) => (
        <Button key={value} type="button" size="sm" variant={language === value ? "secondary" : "ghost"}
          className={compact ? "h-8 px-2 text-xs" : "h-8 px-2.5 text-xs"} aria-pressed={language === value}
          onClick={() => setLanguage(value)}>{value === "bn" ? "\u09ac\u09be\u0982\u09b2\u09be" : "English"}</Button>
      ))}
    </div>
  );
}
