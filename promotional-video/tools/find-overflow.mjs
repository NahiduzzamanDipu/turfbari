// Report elements wider than a phone viewport on a page. node find-overflow.mjs /turfs/green-arena-gulshan
import { launch, page } from "./cdp.mjs";

const path = process.argv[2] ?? "/";
const { session, close } = await launch({ port: 9335 });
const p = page(session, { origin: process.env.TB_ORIGIN ?? "http://localhost:5175" });
await p.viewport(390, 844, { mobile: true });
await p.goto(path, { settle: 2500 });
const report = await p.eval(`(() => {
  const vw = document.documentElement.clientWidth;
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.right > vw + 1 && r.width > 0) {
      const parentOver = el.parentElement && el.parentElement.getBoundingClientRect().right > vw + 1;
      if (!parentOver) out.push({ tag: el.tagName, cls: String(el.className).slice(0, 120), right: Math.round(r.right), width: Math.round(r.width), text: el.innerText?.slice(0, 40) });
    }
  }
  return { vw, scrollWidth: document.documentElement.scrollWidth, out: out.slice(0, 15) };
})()`);
console.log(JSON.stringify(report, null, 1));
close();
