import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { useMe } from "@/features/auth/auth";
import { api } from "@/lib/api";
import en from "@/locales/en";
import bn from "@/locales/bn";

export type Language = "en" | "bn";
type PlatformLanguageSettings = { default_language: Language; new_account_language: Language; visitors_can_switch: boolean };
type LanguageContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  canSwitch: boolean;
  t: (text: string, values?: Record<string, string | number>) => string;
  plural: (count: number, one: string, other: string) => string;
  formatNumber: (value: number, options?: Intl.NumberFormatOptions) => string;
  formatDate: (value: Date | string, options?: Intl.DateTimeFormatOptions) => string;
  formatMoney: (value: string | number) => string;
};

const LANGUAGE_KEY = "turfbari:language";
const PLATFORM_LANGUAGE_KEY = "turfbari:platform-language";
const LanguageContext = createContext<LanguageContextValue | null>(null);
const dictionaries: Record<Language, Record<string, string>> = { en, bn };
const validLanguage = (value: unknown): value is Language => value === "en" || value === "bn";

function savedLanguage(key: string): Language | null {
  try {
    const value = localStorage.getItem(key);
    return validLanguage(value) ? value : null;
  } catch {
    return null;
  }
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const me = useMe();
  const [language, setLanguageState] = useState<Language>(
    () => savedLanguage(LANGUAGE_KEY) ?? savedLanguage(PLATFORM_LANGUAGE_KEY) ?? "en",
  );
  const [settings, setSettings] = useState<PlatformLanguageSettings>({
    default_language: savedLanguage(PLATFORM_LANGUAGE_KEY) ?? "en",
    new_account_language: "en",
    visitors_can_switch: true,
  });
  const hasVisitorChoice = useRef(savedLanguage(LANGUAGE_KEY) !== null);
  const syncedUser = useRef<string | null>(null);

  useEffect(() => {
    let alive = true;
    void api<PlatformLanguageSettings>("/public/language-settings/")
      .then((next) => {
        if (!alive || !validLanguage(next.default_language) || !validLanguage(next.new_account_language)) return;
        setSettings(next);
        try { localStorage.setItem(PLATFORM_LANGUAGE_KEY, next.default_language); } catch { /* storage is optional */ }
        if (!hasVisitorChoice.current && !me.data?.user?.preferred_language) {
          setLanguageState(next.default_language);
        }
      })
      .catch((error: unknown) => console.warn("Could not load platform language settings.", error));
    return () => { alive = false; };
  }, [me.data?.authenticated, me.data?.user?.preferred_language]);

  useEffect(() => {
    const user = me.data?.user;
    if (!me.data?.authenticated || !user) {
      syncedUser.current = null;
      return;
    }
    if (syncedUser.current === user.id) return;
    syncedUser.current = user.id;
    if (validLanguage(user.preferred_language)) {
      hasVisitorChoice.current = true;
      setLanguageState(user.preferred_language);
      try { localStorage.setItem(LANGUAGE_KEY, user.preferred_language); } catch { /* storage is optional */ }
    } else {
      void api("/auth/language/", { method: "PATCH", json: { language } }).catch((error: unknown) => {
        console.warn("Could not sync browser language to the account.", error);
      });
    }
  }, [me.data?.authenticated, me.data?.user?.id, me.data?.user?.preferred_language, language]);

  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dataset.language = language;
  }, [language]);

  const setLanguage = useCallback((next: Language) => {
    hasVisitorChoice.current = true;
    setLanguageState(next);
    try { localStorage.setItem(LANGUAGE_KEY, next); } catch { /* language remains selected for this session */ }
    if (me.data?.authenticated) {
      void api("/auth/language/", { method: "PATCH", json: { language: next } }).catch((error: unknown) => {
        console.warn("Could not save account language preference.", error);
        toast.error(dictionaries[next]["A request to change your language could not be saved."]);
      });
    }
  }, [me.data?.authenticated]);

  const value = useMemo<LanguageContextValue>(() => {
    const locale = language === "bn" ? "bn-BD" : "en-BD";
    const t = (text: string, values?: Record<string, string | number>) => {
      let result = dictionaries[language][text] ?? text;
      if (values) {
        for (const [key, item] of Object.entries(values)) result = result.replaceAll(`{${key}}`, String(item));
      }
      return result;
    };
    return {
      language,
      setLanguage,
      canSwitch: Boolean(me.data?.authenticated || settings.visitors_can_switch),
      t,
      plural: (count, one, other) => {
        const text = new Intl.PluralRules(locale).select(count) === "one" ? one : other;
        return t(text, { count: new Intl.NumberFormat(locale).format(count) });
      },
      formatNumber: (number, options) => new Intl.NumberFormat(locale, options).format(number),
      formatDate: (input, options = { day: "numeric", month: "short", year: "numeric" }) =>
        new Intl.DateTimeFormat(locale, { timeZone: "Asia/Dhaka", ...options }).format(
          typeof input === "string" ? new Date(input) : input,
        ),
      formatMoney: (amount) => new Intl.NumberFormat(locale, {
        style: "currency", currency: "BDT", maximumFractionDigits: 2,
      }).format(Number(amount)),
    };
  }, [language, me.data?.authenticated, setLanguage, settings.visitors_can_switch]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const value = useContext(LanguageContext);
  if (value) return value;
  // Isolated component previews/tests can render outside the application provider.
  return {
    language: "en" as const,
    setLanguage: () => undefined,
    canSwitch: false,
    t: (text: string, values?: Record<string, string | number>) => {
      let result: string = en[text as keyof typeof en] ?? text;
      for (const [key, item] of Object.entries(values ?? {})) result = result.replaceAll(`{${key}}`, String(item));
      return result;
    },
    plural: (count: number, one: string, other: string) => {
      const text = new Intl.PluralRules("en-BD").select(count) === "one" ? one : other;
      let result: string = en[text as keyof typeof en] ?? text;
      return result.replaceAll("{count}", new Intl.NumberFormat("en-BD").format(count));
    },
    formatNumber: (number: number, options?: Intl.NumberFormatOptions) => new Intl.NumberFormat("en-BD", options).format(number),
    formatDate: (input: Date | string, options: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }) =>
      new Intl.DateTimeFormat("en-BD", { timeZone: "Asia/Dhaka", ...options }).format(typeof input === "string" ? new Date(input) : input),
    formatMoney: (amount: string | number) => new Intl.NumberFormat("en-BD", { style: "currency", currency: "BDT", maximumFractionDigits: 2 }).format(Number(amount)),
  };
}
