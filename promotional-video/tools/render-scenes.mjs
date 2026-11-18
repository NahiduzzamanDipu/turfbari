// Render illustrated scenes from scenes.html to PNG.
// node render-scenes.mjs <outDir> <w> <h> scene1 scene2 ...
import { pathToFileURL } from "node:url";
import { join, resolve } from "node:path";
import { launch, page } from "./cdp.mjs";

const [outDir, w, h, ...scenes] = process.argv.slice(2);
const { session, close } = await launch({ port: 9334 });
const p = page(session, { origin: "http://localhost:5175" });
await p.viewport(+w, +h);
const base = pathToFileURL(resolve(import.meta.dirname, "scenes.html")).href;
try {
  for (const scene of scenes) {
    await p.goto(`${base}?scene=${scene}&w=${w}&h=${h}`, { settle: 300 });
    await p.shot(join(outDir, `${scene}.png`), { clip: { x: 0, y: 0, width: +w, height: +h } });
  }
} finally {
  close();
}
