import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const bdt = new Intl.NumberFormat("en-BD", {
  style: "currency",
  currency: "BDT",
  currencyDisplay: "narrowSymbol",
  maximumFractionDigits: 2,
});

/** Formats a decimal string from the API (never a float we computed) as ৳1,200. */
export function formatBDT(amount: string | number): string {
  return bdt.format(Number(amount));
}
