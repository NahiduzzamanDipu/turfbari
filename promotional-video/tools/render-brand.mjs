// Render brand assets (logo PNGs, palette and type sheets) into 01-brand-assets/.
import { copyFileSync, mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { launch, page, writeText } from "./cdp.mjs";

const OUT = resolve(import.meta.dirname, "../01-brand-assets");
const base = pathToFileURL(resolve(import.meta.dirname, "brand.html")).href;
const { session, close } = await launch({ port: 9336 });
const p = page(session, { origin: "http://localhost:5175" });
const transparent = (on) =>
  session.send("Emulation.setDefaultBackgroundColorOverride", on ? { color: { r: 0, g: 0, b: 0, a: 0 } } : {});

try {
  mkdirSync(join(OUT, "logo"), { recursive: true });
  copyFileSync(resolve(import.meta.dirname, "../../frontend/public/favicon.svg"), join(OUT, "logo", "turfbari-mark.svg"));

  for (const [view, w, h, file, clear] of [
    ["mark", 1024, 1024, "logo/turfbari-mark-1024.png", true],
    ["logo-light", 1600, 480, "logo/turfbari-logo-horizontal-transparent.png", true],
    ["logo-light", 1600, 480, "logo/turfbari-logo-horizontal-on-light.png", false],
    ["logo-dark", 1600, 480, "logo/turfbari-logo-horizontal-on-dark.png", false],
    ["logo-dark", 1600, 480, "logo/turfbari-logo-horizontal-light-transparent.png", true],
  ]) {
    await transparent(clear);
    await p.viewport(w, h);
    await p.goto(`${base}?view=${view}${clear ? "&clear=1" : ""}`, { settle: 800 });
    if (!clear && view === "logo-light") await p.eval(`document.body.style.background = getComputedStyle(document.documentElement).getPropertyValue('--background')`);
    await p.shot(join(OUT, file), { clip: { x: 0, y: 0, width: w, height: h } });
  }
  await transparent(false);

  await p.viewport(1920, 1080);
  await p.goto(`${base}?view=palette`, { settle: 800 });
  const palette = await p.eval("window.PALETTE");
  await p.shot(join(OUT, "colors", "turfbari-palette.png"), { fullPage: true });
  writeText(join(OUT, "colors", "palette.json"), JSON.stringify(palette, null, 2));
  writeText(
    join(OUT, "colors", "palette.md"),
    [
      "# TurfBari colours",
      "",
      "Source of truth: `frontend/src/index.css`. HEX/RGB were converted from the oklch tokens by Chrome, so they match what the app renders.",
      "",
      "| Name | Token | HEX | RGB | oklch | Used for |",
      "|---|---|---|---|---|---|",
      ...palette.map((c) => `| ${c.name} | \`--${c.token}\` | \`${c.hex}\` | ${c.rgb} | \`${c.oklch}\` | ${c.use} |`),
      "",
      "Logo file colours (`frontend/public/favicon.svg`): tile `#065F46`, roof `#BEF264`, ball `#FFFFFF`.",
      "",
    ].join("\n"),
  );

  await p.goto(`${base}?view=type`, { settle: 1500 });
  await p.shot(join(OUT, "typography", "turfbari-typography.png"), { fullPage: true });
} finally {
  close();
}
