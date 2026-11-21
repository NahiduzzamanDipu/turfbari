import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InstallAppButton } from "./InstallAppButton";

vi.mock("@/lib/i18n", () => ({ useLanguage: () => ({ t: (key: string) => key }) }));

describe("InstallAppButton", () => {
  it("appears only when the browser offers installation and invokes its prompt", async () => {
    const prompt = vi.fn().mockResolvedValue(undefined);
    const event = new Event("beforeinstallprompt", { cancelable: true }) as Event & {
      prompt: () => Promise<void>;
      userChoice: Promise<{ outcome: "accepted" }>;
    };
    event.prompt = prompt;
    event.userChoice = Promise.resolve({ outcome: "accepted" });

    render(<InstallAppButton />);
    expect(screen.getByRole("button", { name: "Install app" })).toBeInTheDocument();
    act(() => window.dispatchEvent(event));
    fireEvent.click(await screen.findByRole("button", { name: "Install app" }));
    await waitFor(() => expect(prompt).toHaveBeenCalledOnce());
    act(() => window.dispatchEvent(new Event("appinstalled")));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Install app" })).not.toBeInTheDocument());
  });
});
