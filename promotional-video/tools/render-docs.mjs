// Render the storyboard contact sheet (PNG) and print the production guide PDF.
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { launch, page, sleep } from "./cdp.mjs";

const PKG = resolve(import.meta.dirname, "..");
const { session, close } = await launch({ port: 9338 });
const p = page(session, { origin: "http://localhost:5175" });
try {
  await p.viewport(1920, 1080);
  await p.goto(pathToFileURL(join(PKG, "07-storyboard", "storyboard-sheet.html")).href, { settle: 1500 });
  await p.shot(join(PKG, "07-storyboard", "storyboard-sheet.png"), { fullPage: true });

  await p.viewport(1240, 1754);
  await p.goto(pathToFileURL(join(PKG, "10-pdf", "guide.html")).href, { settle: 2500 });
  await p.eval("document.fonts.ready.then(() => true)");
  await sleep(1000);
  await p.pdf(join(PKG, "TurfBari_Bengali_Promotional_Video_Guide.pdf"));
} finally {
  close();
}
