import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PayCard, type RegistrationStatus, StatusCard } from "./RegisterTurfPage";

const receiving = { number: "01999000111", account_type: "Personal", instructions: "Send Money only" };

describe("registration payment UI", () => {
  it("shows the bKash number, the exact discounted amount and copy buttons", () => {
    window.innerWidth = 375; // phone width: same content, stacked
    render(<PayCard receiving={receiving} amount="1600.00" />);
    expect(screen.getByText("01999000111")).toBeInTheDocument();
    expect(screen.getByText(/1,600/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Copy number/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Copy amount/ })).toBeInTheDocument();
    expect(screen.getByText("Send Money only")).toBeInTheDocument();
  });

  it("summarises a submitted registration with the masked transaction ID and the rejection reason", () => {
    const status: RegistrationStatus = {
      reference: "REG-2611-ABCDE",
      turf_name: "New Ground",
      status: "payment_rejected",
      status_label: "Payment not accepted",
      plan: "Monthly",
      promo_code: "TURFSTART20",
      original: "2000.00",
      discount: "400.00",
      payable: "1600.00",
      amount_sent: "1600.00",
      trx: "9C7•••4E",
      submitted_at: "2026-11-21T10:00:00+06:00",
      rejection_reason: "TrxID not found",
      can_resubmit: true,
      receiving,
      history: [],
    };
    render(<StatusCard status={status} />);
    expect(screen.getByText("REG-2611-ABCDE")).toBeInTheDocument();
    expect(screen.getByText("9C7•••4E")).toBeInTheDocument();
    expect(screen.getByText("−৳400.00")).toBeInTheDocument();
    expect(screen.getByText(/TrxID not found/)).toBeInTheDocument();
  });
});
