import { describe, expect, it } from "vitest";
import { linkedSections } from "./PublicLegalPages";

describe("public legal document navigation", () => {
  it("assigns stable section anchors and matching contents labels", () => {
    const prepared = linkedSections("<h2>1. Intro</h2><p>Text</p><h2>2. বাংলা</h2>");
    expect(prepared.sections).toEqual([
      { id: "legal-section-1", title: "1. Intro" },
      { id: "legal-section-2", title: "2. বাংলা" },
    ]);
    const body = new DOMParser().parseFromString(prepared.html, "text/html");
    expect(body.querySelectorAll("h2#legal-section-1")).toHaveLength(1);
    expect(body.querySelectorAll("h2#legal-section-2")).toHaveLength(1);
  });

  it("returns no contents links when a document has no sections", () => {
    expect(linkedSections("<p>Policy text</p>").sections).toEqual([]);
  });
});
