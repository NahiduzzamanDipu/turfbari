// Minimal Chrome DevTools Protocol driver (Node 22+, no npm packages).
// Used to capture real TurfBari screenshots and to print the production PDF.
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";

const CHROME_CANDIDATES = [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
];

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function launch({ port = 9333 } = {}) {
  const exe = process.env.CHROME_PATH ?? CHROME_CANDIDATES[0];
  const profile = join(tmpdir(), `turfbari-capture-${Date.now()}`);
  const proc = spawn(
    exe,
    [
      "--headless=new",
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${profile}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--hide-scrollbars",
      "--force-device-scale-factor=1",
      "--lang=en-GB",
      "about:blank",
    ],
    { stdio: "ignore" },
  );
  let version;
  for (let i = 0; i < 50 && !version; i++) {
    await sleep(200);
    version = await fetch(`http://127.0.0.1:${port}/json/version`).then((r) => r.json()).catch(() => null);
  }
  if (!version) throw new Error("Chrome did not start");
  const targets = await fetch(`http://127.0.0.1:${port}/json/list`).then((r) => r.json());
  const page = targets.find((t) => t.type === "page");
  const session = await connect(page.webSocketDebuggerUrl);
  return { session, close: () => proc.kill() };
}

async function connect(url) {
  const ws = new WebSocket(url);
  await new Promise((res, rej) => {
    ws.onopen = res;
    ws.onerror = rej;
  });
  let id = 0;
  const pending = new Map();
  const listeners = new Map();
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(`${msg.error.message} ${msg.error.data ?? ""}`)) : resolve(msg.result);
    } else if (msg.method) {
      for (const fn of listeners.get(msg.method) ?? []) fn(msg.params);
    }
  };
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const n = ++id;
      pending.set(n, { resolve, reject });
      ws.send(JSON.stringify({ id: n, method, params }));
    });
  const once = (method) =>
    new Promise((resolve) => {
      const fn = (p) => {
        listeners.set(method, (listeners.get(method) ?? []).filter((f) => f !== fn));
        resolve(p);
      };
      listeners.set(method, [...(listeners.get(method) ?? []), fn]);
    });
  await send("Page.enable");
  await send("Runtime.enable");
  return { send, once };
}

export function page(session, { origin }) {
  const { send, once } = session;
  const api = {
    async viewport(width, height, { mobile = false } = {}) {
      await send("Emulation.setDeviceMetricsOverride", {
        width,
        height,
        deviceScaleFactor: 1,
        mobile,
        screenWidth: width,
        screenHeight: height,
      });
      await send("Emulation.setTouchEmulationEnabled", { enabled: mobile });
    },
    async geolocation(latitude, longitude) {
      await send("Browser.grantPermissions", { origin, permissions: ["geolocation"] }).catch(() => {});
      await send("Emulation.setGeolocationOverride", { latitude, longitude, accuracy: 30 });
    },
    async colorScheme(value) {
      await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value }] });
    },
    async goto(path, { settle = 1800 } = {}) {
      const url = path.startsWith("http") || path.startsWith("file:") ? path : origin + path;
      for (let attempt = 1; attempt <= 6; attempt++) {
        const loaded = once("Page.loadEventFired");
        await send("Page.navigate", { url });
        await loaded;
        await api.settle(settle);
        // The dev backend auto-reloads when code changes; retry pages that caught it mid-restart.
        const broken = await api.eval(`/Couldn't load this|Something went wrong/.test(document.body.innerText)`);
        if (!broken || url.startsWith("file:")) return;
        console.warn(`  retry ${attempt}: ${path} hit an API error`);
        await sleep(3000 * attempt);
      }
      throw new Error(`page kept failing: ${path}`);
    },
    async settle(ms = 1200) {
      // wait for fonts, images and React Query skeletons to finish
      for (let i = 0; i < 40; i++) {
        const busy = await api.eval(`(() => {
          const imgs = [...document.images].filter(i => !i.complete).length;
          const skel = document.querySelectorAll('[data-slot="skeleton"], .animate-pulse').length;
          return imgs + skel + (document.fonts.status === 'loaded' ? 0 : 1);
        })()`);
        if (!busy) break;
        await sleep(150);
      }
      await sleep(ms);
    },
    async eval(expression) {
      const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
      return r.result.value;
    },
    /** Click the first visible element whose text (or aria-label) contains `text`. */
    async click(text, { selector = "button, a, [role=radio], [role=button], label" } = {}) {
      const ok = await api.eval(`(() => {
        const want = ${JSON.stringify(text)};
        const el = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e =>
          (e.innerText?.trim().includes(want) || e.getAttribute('aria-label')?.includes(want)) && e.offsetParent !== null);
        if (!el) return false;
        el.scrollIntoView({ block: 'center' });
        el.click();
        return true;
      })()`);
      if (!ok) throw new Error(`click: nothing matches "${text}"`);
      await sleep(500);
    },
    /** Fill an input/textarea found by label text or placeholder, the React-compatible way. */
    async fill(label, value) {
      const ok = await api.eval(`(() => {
        const want = ${JSON.stringify(label)};
        let el = [...document.querySelectorAll('input, textarea')].find(e => e.placeholder === want || e.getAttribute('aria-label') === want);
        if (!el) {
          const lab = [...document.querySelectorAll('label')].find(l => l.innerText.trim().startsWith(want));
          el = lab && (lab.htmlFor ? document.getElementById(lab.htmlFor) : lab.querySelector('input, textarea'));
        }
        if (!el) return false;
        const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, ${JSON.stringify(value)});
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      })()`);
      if (!ok) throw new Error(`fill: no field "${label}"`);
      await sleep(150);
    },
    async scrollTo(textOrY) {
      if (typeof textOrY === "number") await api.eval(`window.scrollTo(0, ${textOrY})`);
      else
        await api.eval(`(() => {
          const want = ${JSON.stringify(textOrY)};
          const el = [...document.querySelectorAll('h1,h2,h3,p,span,div,section,label,button')].find(e => e.childElementCount < 4 && e.innerText?.trim().startsWith(want));
          if (el) el.scrollIntoView({ block: 'start' });
          window.scrollBy(0, -90);
        })()`);
      await sleep(600);
    },
    async shot(file, { fullPage = false, clip } = {}) {
      mkdirSync(dirname(file), { recursive: true });
      const params = { format: "png", captureBeyondViewport: fullPage };
      if (clip) params.clip = { ...clip, scale: 1 };
      if (fullPage) {
        const h = await api.eval("document.documentElement.scrollHeight");
        const w = await api.eval("document.documentElement.clientWidth");
        params.clip = { x: 0, y: 0, width: w, height: Math.min(h, 6000), scale: 1 };
      }
      const { data } = await send("Page.captureScreenshot", params);
      writeFileSync(file, Buffer.from(data, "base64"));
      console.log("saved", file);
    },
    async pdf(file, options = {}) {
      mkdirSync(dirname(file), { recursive: true });
      const { data } = await send("Page.printToPDF", {
        printBackground: true,
        preferCSSPageSize: true,
        displayHeaderFooter: false,
        ...options,
      });
      writeFileSync(file, Buffer.from(data, "base64"));
      console.log("saved", file);
    },
    async login(email, password) {
      const status = await api.eval(`(async () => {
        await fetch('/api/auth/logout/', { method: 'POST', credentials: 'same-origin',
          headers: { 'X-CSRFToken': (document.cookie.match(/turfbari_csrftoken=([^;]+)/) || [])[1] || '' } }).catch(() => {});
        await fetch('/api/auth/csrf/', { credentials: 'same-origin' });
        const token = (document.cookie.match(/turfbari_csrftoken=([^;]+)/) || [])[1];
        const r = await fetch('/api/auth/login/', { method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
          body: JSON.stringify({ identifier: ${JSON.stringify(email)}, password: ${JSON.stringify(password)} }) });
        return r.status;
      })()`);
      if (status !== 200) throw new Error(`login failed for ${email}: ${status}`);
    },
    async logout() {
      await api.eval(`fetch('/api/auth/logout/', { method: 'POST', credentials: 'same-origin',
        headers: { 'X-CSRFToken': (document.cookie.match(/turfbari_csrftoken=([^;]+)/) || [])[1] || '' } })`);
    },
  };
  return api;
}

export function writeText(file, text) {
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, text);
}
