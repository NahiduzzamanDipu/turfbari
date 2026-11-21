import { Download } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/form";
import { useLanguage } from "@/lib/i18n";

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export function InstallAppButton() {
  const [promptEvent, setPromptEvent] = useState<InstallPromptEvent | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [installed, setInstalled] = useState(false);
  const { t, language } = useLanguage();

  useEffect(() => {
    const standalone = window.matchMedia?.("(display-mode: standalone)");
    const syncInstalled = () => setInstalled(Boolean(standalone?.matches || (navigator as Navigator & { standalone?: boolean }).standalone));
    syncInstalled();
    standalone?.addEventListener("change", syncInstalled);
    const capture = (event: Event) => {
      event.preventDefault();
      setPromptEvent(event as InstallPromptEvent);
    };
    const onInstalled = () => {
      setInstalled(true);
      setPromptEvent(null);
    };
    window.addEventListener("beforeinstallprompt", capture);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      standalone?.removeEventListener("change", syncInstalled);
      window.removeEventListener("beforeinstallprompt", capture);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (installed) return null;

  const install = async () => {
    if (!promptEvent) {
      setShowHelp(true);
      return;
    }
    try {
      await promptEvent.prompt();
      await promptEvent.userChoice;
    } finally {
      setPromptEvent(null);
    }
  };

  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => void install()}>
        <Download aria-hidden="true" /> {t("Install app")}
      </Button>
      <Dialog open={showHelp} onClose={() => setShowHelp(false)} title={t("Install app")}>
        <div className="space-y-3 text-sm leading-relaxed">
          {language === "bn" ? (
            <>
              <p><strong>iPhone বা iPad:</strong> Safari-তে Share চাপুন, তারপর “Add to Home Screen” নির্বাচন করুন।</p>
              <p><strong>Android:</strong> Chrome-এর মেনু খুলে “Install app” অথবা “Add to Home screen” চাপুন।</p>
              <p>ইনস্টল অপশন না থাকলে পেজটি রিলোড করে আবার চেষ্টা করুন।</p>
            </>
          ) : (
            <>
              <p><strong>iPhone or iPad:</strong> In Safari, tap Share, then choose “Add to Home Screen”.</p>
              <p><strong>Android:</strong> Open the Chrome menu and choose “Install app” or “Add to Home screen”.</p>
              <p>If the install option is missing, reload this page and try again.</p>
            </>
          )}
        </div>
      </Dialog>
    </>
  );
}
