// Render the reference frames listed in 07-storyboard/frames.json into 03-reference-images/scene-XX/.
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { launch, page } from "./cdp.mjs";

const PKG = resolve(import.meta.dirname, "..");
const frames = JSON.parse(readFileSync(join(PKG, "07-storyboard", "frames.json"), "utf8"));
const root = pathToFileURL(PKG).href + "/";
const { session, close } = await launch({ port: 9337 });
const p = page(session, { origin: "http://localhost:5175" });
await p.viewport(1920, 1080);
await p.goto(pathToFileURL(resolve(import.meta.dirname, "frames.html")).href, { settle: 500 });
let broken = 0;
try {
  for (const [id, frame] of Object.entries(frames)) {
    const missing = await p.eval(`window.renderFrame(${JSON.stringify({ ...frame, root })})`);
    if (missing.length) {
      broken++;
      console.error("MISSING IMAGES in", id, missing);
    }
    const scene = id.slice(1, 3);
    await p.shot(join(PKG, "03-reference-images", `scene-${scene}`, `${id}.png`), {
      clip: { x: 0, y: 0, width: 1920, height: 1080 },
    });
  }
} finally {
  close();
}
if (broken) process.exit(1);
