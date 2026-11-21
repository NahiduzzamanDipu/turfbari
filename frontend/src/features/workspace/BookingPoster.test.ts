import { describe, expect, it } from "vitest";
import { markPngAs300Dpi } from "./BookingPoster";

describe("booking poster PNG export", () => {
  it("adds a valid 300 DPI pHYs chunk after the PNG header", async () => {
    const sample = Uint8Array.from(
      atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9ioAAAAASUVORK5CYII="),
      (character) => character.charCodeAt(0),
    );
    const blob = await markPngAs300Dpi(new Blob([sample]));
    const bytes = new Uint8Array(await blob.arrayBuffer());
    const view = new DataView(bytes.buffer);
    const chunkOffset = 8 + 4 + 4 + 13 + 4;

    expect(blob.type).toBe("image/png");
    expect(new TextDecoder().decode(bytes.slice(chunkOffset + 4, chunkOffset + 8))).toBe("pHYs");
    expect(view.getUint32(chunkOffset)).toBe(9);
    expect(view.getUint32(chunkOffset + 8)).toBe(11811);
    expect(view.getUint32(chunkOffset + 12)).toBe(11811);
    expect(bytes[chunkOffset + 16]).toBe(1);
  });
});
