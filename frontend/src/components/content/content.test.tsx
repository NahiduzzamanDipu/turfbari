import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { clearDraft, loadDraft, saveDraft, visitorId } from "@/lib/visitor";
import { FormattedText } from "./FormattedText";
import { YouTubeDialog } from "./YouTube";

function VideoButton({ id }: { id: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        বুকিং করার নিয়ম
      </button>
      {open && <YouTubeDialog videoId={id} title="How to book" onClose={() => setOpen(false)} />}
    </>
  );
}

describe("YouTube popup", () => {
  it("opens the nocookie embed without autoplay and removes the player on close", () => {
    const { container } = render(<VideoButton id="aqz-KE-bpKQ" />);
    expect(document.querySelector("iframe")).toBeNull();
    fireEvent.click(screen.getByText("বুকিং করার নিয়ম"));
    const frame = document.querySelector("iframe")!;
    expect(frame.src).toBe("https://www.youtube-nocookie.com/embed/aqz-KE-bpKQ?rel=0&modestbranding=1");
    expect(frame.src).not.toContain("autoplay");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.querySelector("iframe")).toBeNull(); // unmounted => playback stops
    expect(container).toBeTruthy();
  });

  it("never embeds something that isn't a video id", () => {
    render(<YouTubeDialog videoId={'x" onload="alert(1)'} title="Bad" onClose={() => undefined} />);
    expect(document.querySelector("iframe")).toBeNull();
    expect(screen.getByText("This video can't be played.")).toBeTruthy();
  });
});

describe("Terms text", () => {
  it("renders headings, lists and bold but never raw HTML", () => {
    const { container } = render(
      <FormattedText text={"# নিয়মাবলী\n- **সময়মতো** আসুন\n1. Pay the advance\n\n<img src=x onerror=alert(1)>"} />,
    );
    expect(container.querySelector("h2")?.textContent).toBe("নিয়মাবলী");
    expect(container.querySelector("ul li strong")?.textContent).toBe("সময়মতো");
    expect(container.querySelector("ol li")?.textContent).toBe("Pay the advance");
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});

describe("Booking draft storage", () => {
  it("keeps a stable visitor id and a draft without personal data, and clears it", () => {
    const id = visitorId();
    expect(visitorId()).toBe(id);
    saveDraft("green-arena", { fieldId: "f1", day: "2026-11-22", token: "tok" });
    const draft = loadDraft("green-arena")!;
    expect(draft).toMatchObject({ fieldId: "f1", day: "2026-11-22", token: "tok" });
    expect(draft.idempotencyKey).toMatch(/^[0-9a-f-]{36}$/);
    expect(JSON.stringify(localStorage)).not.toMatch(/01[3-9]\d{8}/);
    clearDraft("green-arena");
    expect(loadDraft("green-arena")).toBeNull();
  });

  it("forgets drafts older than 30 minutes", () => {
    saveDraft("old", { fieldId: "f", day: "2026-11-22", token: "t" });
    const raw = JSON.parse(localStorage.getItem("turfbari:draft:old")!);
    localStorage.setItem("turfbari:draft:old", JSON.stringify({ ...raw, savedAt: Date.now() - 31 * 60_000 }));
    expect(loadDraft("old")).toBeNull();
  });
});

describe("SMS part counter (matches the server)", () => {
  it("counts English and Bengali parts like BulkSMSBD bills them", async () => {
    const { smsSegments } = await import("@/features/sms/WalletPages");
    expect(smsSegments("a".repeat(160)).segments).toBe(1);
    expect(smsSegments("a".repeat(161)).segments).toBe(2);
    expect(smsSegments("ক".repeat(70))).toMatchObject({ unicode: true, segments: 1 });
    expect(smsSegments("ক".repeat(71)).segments).toBe(2);
    expect(smsSegments("ক".repeat(140)).segments).toBe(3);
  });
});
