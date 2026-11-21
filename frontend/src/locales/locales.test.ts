import { describe, expect, it } from "vitest";
import en from "./en";
import bn from "./bn";

describe("platform translation resources", () => {
  it("provide a Bengali translation for each English resource key", () => {
    expect(Object.keys(bn).sort()).toEqual(Object.keys(en).sort());
  });

  it("contain readable Bengali text and preserve English fallback labels", () => {
    expect(bn.Dashboard).toBe(String.fromCodePoint(0x09a1, 0x09cd, 0x09af, 0x09be, 0x09b6, 0x09ac, 0x09cb, 0x09b0, 0x09cd, 0x09a1));
    expect(bn.API).toBe("API");
    expect(en.Dashboard).toBe("Dashboard");
  });
});
