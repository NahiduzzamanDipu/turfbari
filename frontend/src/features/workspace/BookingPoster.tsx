import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/form";
import { api } from "@/lib/api";
import type { TurfSettings } from "@/lib/types";
import { useLanguage } from "@/lib/i18n";

const WIDTH = 2480;
const HEIGHT = 3508;
const GREEN = "#064e3b";
const LIME = "#bef264";
const MINT = "#d1fae5";

type PosterInfo = { booking_url: string; website_url: string };
let posterFontsPromise: Promise<void> | null = null;

function ensurePosterFonts() {
  if (!posterFontsPromise) {
    const fonts: [string, string][] = [
      ["500", "/fonts/HindSiliguri-Medium.ttf"],
      ["600", "/fonts/HindSiliguri-SemiBold.ttf"],
      ["700", "/fonts/HindSiliguri-Bold.ttf"],
    ];
    posterFontsPromise = Promise.all(fonts.map(async ([weight, url]) => {
      const face = new FontFace("Hind Siliguri", `url(${url})`, { weight });
      await face.load();
      document.fonts.add(face);
    })).then(() => undefined);
  }
  return posterFontsPromise;
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Poster image could not be loaded."));
    image.src = src;
  });
}

function wrappedLines(ctx: CanvasRenderingContext2D, text: string, maxWidth: number) {
  const lines: string[] = [];
  let line = "";
  for (const word of text.trim().split(/\s+/)) {
    const candidate = line ? `${line} ${word}` : word;
    if (line && ctx.measureText(candidate).width > maxWidth) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  }
  if (line) lines.push(line);
  return lines;
}

function drawLight(ctx: CanvasRenderingContext2D, x: number, y: number) {
  const glow = ctx.createRadialGradient(x, y, 4, x, y, 520);
  glow.addColorStop(0, "rgba(225,255,226,.25)");
  glow.addColorStop(.18, "rgba(140,255,169,.10)");
  glow.addColorStop(1, "rgba(140,255,169,0)");
  ctx.fillStyle = glow;
  ctx.fillRect(x - 520, y - 120, 1040, 1040);
  ctx.save();
  ctx.strokeStyle = "rgba(229,255,226,.25)";
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.moveTo(x - 145, y - 36);
  ctx.lineTo(x - 300, y + 220);
  ctx.moveTo(x + 145, y - 36);
  ctx.lineTo(x + 300, y + 220);
  ctx.stroke();
  ctx.fillStyle = "#eaffee";
  for (let lamp = -2; lamp <= 2; lamp++) {
    ctx.beginPath();
    ctx.arc(x + lamp * 34, y, 9, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

function drawPitch(ctx: CanvasRenderingContext2D) {
  // Fine diagonal grass strokes give the page texture without distracting from the content.
  ctx.save();
  ctx.globalAlpha = .15;
  for (let i = 0; i < 740; i++) {
    const x = (i * 137) % WIDTH;
    const y = (i * 283) % HEIGHT;
    const length = 18 + (i % 5) * 7;
    ctx.strokeStyle = i % 2 ? "#8fcf63" : "#b0df74";
    ctx.lineWidth = i % 4 === 0 ? 3 : 2;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + length * .55, y - length);
    ctx.stroke();
  }
  ctx.restore();

  // Oversized, low-contrast pitch markings frame the poster as a ground, not a blank sheet.
  ctx.save();
  ctx.strokeStyle = "rgba(224,255,226,.12)";
  ctx.lineWidth = 7;
  ctx.strokeRect(78, 90, WIDTH - 156, HEIGHT - 180);
  ctx.beginPath();
  ctx.moveTo(80, HEIGHT * .52);
  ctx.lineTo(WIDTH - 80, HEIGHT * .52);
  ctx.arc(WIDTH / 2, HEIGHT * .52, 365, 0, Math.PI * 2);
  ctx.stroke();
  ctx.strokeRect(80, HEIGHT * .34, 455, 700);
  ctx.strokeRect(WIDTH - 535, HEIGHT * .34, 455, 700);
  ctx.strokeRect(80, HEIGHT * .68, 455, 700);
  ctx.strokeRect(WIDTH - 535, HEIGHT * .68, 455, 700);
  ctx.restore();
}

function drawInfoIcon(ctx: CanvasRenderingContext2D, kind: "pin" | "phone", x: number, y: number) {
  ctx.save();
  ctx.strokeStyle = LIME;
  ctx.lineWidth = 9;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  if (kind === "pin") {
    ctx.arc(x, y - 9, 26, Math.PI * .15, Math.PI * .85);
    ctx.quadraticCurveTo(x, y + 58, x, y + 58);
    ctx.quadraticCurveTo(x, y + 58, x - 26, y + 1);
    ctx.moveTo(x - 11, y - 9);
    ctx.arc(x, y - 9, 11, Math.PI, Math.PI * 3);
  } else {
    ctx.moveTo(x - 26, y - 35);
    ctx.quadraticCurveTo(x - 42, y - 43, x - 44, y - 22);
    ctx.quadraticCurveTo(x - 29, y + 30, x + 19, y + 46);
    ctx.quadraticCurveTo(x + 42, y + 48, x + 42, y + 24);
    ctx.lineTo(x + 19, y + 7);
    ctx.lineTo(x + 2, y + 23);
    ctx.quadraticCurveTo(x - 13, y + 13, x - 18, y - 2);
    ctx.lineTo(x - 4, y - 18);
    ctx.closePath();
  }
  ctx.stroke();
  ctx.restore();
}

function drawPoster(
  canvas: HTMLCanvasElement,
  turf: TurfSettings,
  info: PosterInfo,
  qr: HTMLImageElement,
  turfLogo: HTMLImageElement | null,
  brandMark: HTMLImageElement,
  language: string,
) {
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Poster canvas is unavailable in this browser.");
  canvas.width = WIDTH;
  canvas.height = HEIGHT;

  // Full-bleed stadium night scene. The QR is painted later on an opaque white panel.
  const ground = ctx.createLinearGradient(0, 0, WIDTH * .8, HEIGHT);
  ground.addColorStop(0, "#061e18");
  ground.addColorStop(.43, "#0a4a32");
  ground.addColorStop(.76, "#12653e");
  ground.addColorStop(1, "#06251b");
  ctx.fillStyle = ground;
  ctx.fillRect(0, 0, WIDTH, HEIGHT);
  drawPitch(ctx);
  drawLight(ctx, 150, 105);
  drawLight(ctx, WIDTH - 150, 105);
  const vignette = ctx.createRadialGradient(WIDTH / 2, HEIGHT * .42, 360, WIDTH / 2, HEIGHT * .42, HEIGHT * .78);
  vignette.addColorStop(0, "rgba(3,23,17,0)");
  vignette.addColorStop(1, "rgba(1,14,11,.52)");
  ctx.fillStyle = vignette;
  ctx.fillRect(0, 0, WIDTH, HEIGHT);

  // Turf identity badge: contain the real logo so it is never stretched or cropped.
  const center = WIDTH / 2;
  const logoSize = 246;
  const logoY = 122;
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,.38)";
  ctx.shadowBlur = 28;
  ctx.fillStyle = "#ffffff";
  ctx.beginPath();
  ctx.arc(center, logoY + logoSize / 2, logoSize / 2 + 13, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  ctx.save();
  ctx.beginPath();
  ctx.arc(center, logoY + logoSize / 2, logoSize / 2, 0, Math.PI * 2);
  ctx.clip();
  ctx.fillStyle = "#f4fff4";
  ctx.fillRect(center - logoSize / 2, logoY, logoSize, logoSize);
  if (turfLogo) {
    const scale = Math.min((logoSize - 30) / turfLogo.width, (logoSize - 30) / turfLogo.height);
    const w = turfLogo.width * scale;
    const h = turfLogo.height * scale;
    ctx.drawImage(turfLogo, center - w / 2, logoY + (logoSize - h) / 2, w, h);
  } else {
    const initials = turf.name.trim().split(/\s+/).slice(0, 2).map((part) => part[0] ?? "").join("");
    ctx.fillStyle = GREEN;
    ctx.font = "800 104px Inter, 'Hind Siliguri', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(initials, center, logoY + logoSize / 2, logoSize - 30);
  }
  ctx.restore();

  // Oversized, adaptable turf name; keep the full name visible, including long names.
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  const nameMaxWidth = 2200;
  let nameSize = 132;
  let nameLines: string[] = [];
  do {
    ctx.font = `800 ${nameSize}px 'Hind Siliguri', Inter, 'Noto Sans Bengali', sans-serif`;
    nameLines = wrappedLines(ctx, turf.name, nameMaxWidth);
    if (nameLines.length <= 2 || nameSize <= 54) break;
    nameSize -= 6;
  } while (nameSize > 54);
  ctx.fillStyle = "#ffffff";
  ctx.shadowColor = "rgba(0,0,0,.45)";
  ctx.shadowBlur = 18;
  let y = 500;
  for (const line of nameLines) {
    ctx.fillText(line, center, y, nameMaxWidth);
    y += nameSize * 1.08;
  }
  ctx.shadowBlur = 0;

  // Two bold information bands, compact when either optional value is absent.
  const infoTop = Math.max(850, y + 38);
  const hasAddress = Boolean(turf.address.trim());
  const hasPhone = Boolean(turf.public_phone.trim());
  let addressSize = 55;
  let addressLines: string[] = [];
  if (hasAddress) {
    do {
      ctx.font = `600 ${addressSize}px 'Hind Siliguri', Inter, 'Noto Sans Bengali', sans-serif`;
      addressLines = wrappedLines(ctx, turf.address, 1950);
      if (addressLines.length <= 2 || addressSize <= 39) break;
      addressSize -= 2;
    } while (addressSize > 39);
  }
  const infoHeight = hasAddress && hasPhone
    ? Math.max(300, 190 + addressLines.length * 66)
    : hasAddress
      ? Math.max(190, 190 + addressLines.length * 66)
      : hasPhone ? 190 : 0;
  if (infoHeight) {
    ctx.save();
    ctx.fillStyle = "rgba(2,31,23,.74)";
    ctx.fillRect(112, infoTop, WIDTH - 224, infoHeight);
    ctx.fillStyle = LIME;
    ctx.fillRect(112, infoTop, 12, infoHeight);
    ctx.restore();
  }
  let infoY = infoTop + (hasAddress && hasPhone ? 100 : 118);
  if (turf.address.trim()) {
    drawInfoIcon(ctx, "pin", 205, infoY - 20);
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillStyle = MINT;
    ctx.font = `600 ${addressSize}px 'Hind Siliguri', Inter, 'Noto Sans Bengali', sans-serif`;
    for (const line of addressLines) {
      ctx.fillText(line, 275, infoY, 1950);
      infoY += 66;
    }
  }
  if (turf.public_phone.trim()) {
    const phoneY = turf.address.trim() ? infoTop + infoHeight - 76 : infoY;
    drawInfoIcon(ctx, "phone", 205, phoneY);
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillStyle = LIME;
    ctx.font = "800 66px Inter, 'Hind Siliguri', sans-serif";
    ctx.fillText(turf.public_phone, 275, phoneY, 1950);
  }

  // Sport-event callout and high-contrast booking code.
  const headlineY = infoTop + infoHeight + 166;
  ctx.save();
  ctx.translate(center, headlineY - 56);
  ctx.rotate(-.018);
  ctx.fillStyle = LIME;
  ctx.fillRect(-1120, -95, 2240, 190);
  ctx.fillStyle = "#073c31";
  ctx.font = language === "bn"
    ? "800 105px 'Hind Siliguri', sans-serif"
    : "900 118px Inter, Arial, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const headline = language === "bn"
    ? "\u0986\u09aa\u09a8\u09be\u09b0 \u0996\u09c7\u09b2\u09be \u09ac\u09c1\u0995 \u0995\u09b0\u09c1\u09a8!"
    : "BOOK YOUR GAME!";
  ctx.fillText(headline, 0, 0, 2100);
  ctx.restore();

  const instructionY = headlineY + 132;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#ffffff";
  ctx.font = language === "bn"
    ? "800 63px 'Hind Siliguri', sans-serif"
    : "800 62px Inter, Arial, sans-serif";
  const instruction = language === "bn"
    ? "\u09ac\u09c1\u0995 \u0995\u09b0\u09a4\u09c7 QR \u0995\u09cb\u09a1 \u09b8\u09cd\u0995\u09cd\u09af\u09be\u09a8 \u0995\u09b0\u09c1\u09a8"
    : "SCAN TO BOOK NOW";
  ctx.fillText(instruction, center, instructionY, 2100);

  const boxY = instructionY + 86;
  const footerHeight = 420;
  const footerGap = 112;
  const box = Math.min(1450, HEIGHT - footerHeight - footerGap - boxY);
  if (box < 950) throw new Error("The poster content is too long to fit on one page; shorten the turf details.");
  const boxX = center - box / 2;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(boxX - 30, boxY - 30, box + 60, box + 60);
  ctx.strokeStyle = LIME;
  ctx.lineWidth = 12;
  ctx.strokeRect(boxX - 30, boxY - 30, box + 60, box + 60);
  const qrSize = box - 70;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(qr, center - qrSize / 2, boxY + (box - qrSize) / 2, qrSize, qrSize);
  ctx.imageSmoothingEnabled = true;

  // Branded footer fills the page base while keeping the turf as the hero.
  const footerY = boxY + box + footerGap;
  const footer = ctx.createLinearGradient(0, footerY, WIDTH, footerY + 420);
  footer.addColorStop(0, "#041d17");
  footer.addColorStop(.5, "#063728");
  footer.addColorStop(1, "#041d17");
  ctx.fillStyle = footer;
  ctx.fillRect(0, footerY, WIDTH, HEIGHT - footerY);
  ctx.fillStyle = LIME;
  ctx.fillRect(0, footerY, WIDTH, 12);
  const markSize = 132;
  const brandY = footerY + 72;
  ctx.drawImage(brandMark, center - 410, brandY, markSize, markSize);
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#ffffff";
  ctx.font = "900 84px Inter, Arial, sans-serif";
  ctx.fillText("TURFBARI", center - 250, brandY + 66);
  ctx.fillStyle = LIME;
  ctx.textAlign = "center";
  ctx.font = "700 30px Inter, Arial, sans-serif";
  ctx.fillText("POWERED BY", center, brandY + 164);
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = MINT;
  ctx.font = "600 46px Inter, Arial, sans-serif";
  ctx.fillText(info.website_url, center, footerY + 320, 2200);
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function markPngAs300Dpi(blob: Blob): Promise<Blob> {
  const png = new Uint8Array(await blob.arrayBuffer());
  const chunkData = new Uint8Array(9);
  const dataView = new DataView(chunkData.buffer);
  dataView.setUint32(0, 11811); // 300 pixels per inch, expressed as pixels per metre.
  dataView.setUint32(4, 11811);
  chunkData[8] = 1;

  const type = new TextEncoder().encode("pHYs");
  const crcInput = new Uint8Array(type.length + chunkData.length);
  crcInput.set(type);
  crcInput.set(chunkData, type.length);
  let crc = 0xffffffff;
  for (const byte of crcInput) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
  }
  crc = (crc ^ 0xffffffff) >>> 0;

  const chunk = new Uint8Array(4 + type.length + chunkData.length + 4);
  const chunkView = new DataView(chunk.buffer);
  chunkView.setUint32(0, chunkData.length);
  chunk.set(type, 4);
  chunk.set(chunkData, 8);
  chunkView.setUint32(chunk.length - 4, crc);

  // PNG's first chunk is IHDR; pHYs must follow it and precede IDAT.
  const insertAt = 8 + 4 + 4 + 13 + 4;
  const toBuffer = (bytes: Uint8Array) => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
  return new Blob([toBuffer(png.slice(0, insertAt)), toBuffer(chunk), toBuffer(png.slice(insertAt))], { type: "image/png" });
}

async function canvasPdf(canvas: HTMLCanvasElement): Promise<Blob> {
  const data = canvas.toDataURL("image/jpeg", 0.98).split(",")[1] ?? "";
  const jpeg = Uint8Array.from(atob(data), (character) => character.charCodeAt(0));
  const encoder = new TextEncoder();
  const parts: Uint8Array[] = [];
  let length = 0;
  const append = (part: Uint8Array) => {
    parts.push(part);
    length += part.length;
  };
  const ascii = (value: string) => encoder.encode(value);
  append(ascii("%PDF-1.4\n% TurfBari poster\n"));
  const offsets = [0];
  const object = (id: number, data: Uint8Array[]) => {
    offsets[id] = length;
    append(ascii(`${id} 0 obj\n`));
    for (const part of data) append(part);
    append(ascii("\nendobj\n"));
  };
  object(1, [ascii("<< /Type /Catalog /Pages 2 0 R >>")]);
  object(2, [ascii("<< /Type /Pages /Kids [3 0 R] /Count 1 >>")]);
  object(3, [ascii("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] /Resources << /XObject << /Poster 4 0 R >> >> /Contents 5 0 R >>")]);
  object(4, [
    ascii(`<< /Type /XObject /Subtype /Image /Width ${canvas.width} /Height ${canvas.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`),
    jpeg,
    ascii("\nendstream"),
  ]);
  const content = ascii("q\n595.28 0 0 841.89 0 0 cm\n/Poster Do\nQ\n");
  object(5, [ascii(`<< /Length ${content.length} >>\nstream\n`), content, ascii("endstream")]);
  const xref = length;
  append(ascii(`xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("")}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`));
  const toBuffer = (bytes: Uint8Array) => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
  return new Blob(parts.map(toBuffer), { type: "application/pdf" });
}

export function BookingPoster({ turf, published }: { turf: TurfSettings; published: boolean }) {
  const { language, t } = useLanguage();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [renderError, setRenderError] = useState("");
  const [rendering, setRendering] = useState(true);
  const [downloading, setDownloading] = useState<"png" | "pdf" | null>(null);
  const info = useQuery({
    queryKey: ["ws", "booking-poster-info", turf.slug],
    queryFn: () => api<PosterInfo>("/workspace/booking-page/poster-info/"),
  });

  useEffect(() => {
    let active = true;
    async function render() {
      if (!info.data || !canvas.current) return;
      setRendering(true);
      setRenderError("");
      try {
        const booking = new URL(info.data.booking_url);
        const site = new URL(info.data.website_url);
        if (booking.origin !== site.origin || booking.pathname !== `/turfs/${turf.slug}`) {
          throw new Error(t("The public booking URL is unavailable or does not match this turf."));
        }
        await ensurePosterFonts();
        await document.fonts.ready;
        const qr = await loadImage(`/api/workspace/booking-page/qr.svg?scale=32`);
        const brandMark = await loadImage("/favicon.svg");
        const turfLogo = turf.profile_image_url
          ? await loadImage(new URL(turf.profile_image_url, window.location.origin).href).catch(() => null)
          : null;
        if (!active || !canvas.current) return;
        drawPoster(canvas.current, turf, info.data, qr, turfLogo, brandMark, language);
      } catch (error) {
        if (active) setRenderError(error instanceof Error ? error.message : t("The poster preview could not be generated."));
      } finally {
        if (active) setRendering(false);
      }
    }
    void render();
    return () => { active = false; };
  }, [info.data, turf.name, turf.slug, turf.address, turf.public_phone, turf.profile_image_url, language, t]);

  const filename = turf.slug.replace(/[^a-z0-9-]/gi, "-") || "turf";
  async function download(format: "png" | "pdf") {
    const target = canvas.current;
    if (!target || !published || rendering || renderError) return;
    setDownloading(format);
    try {
      if (format === "png") {
        const blob = await new Promise<Blob>((resolve, reject) =>
          target.toBlob((value) => value ? resolve(value) : reject(new Error(t("The PNG could not be created."))), "image/png"),
        );
        downloadBlob(await markPngAs300Dpi(blob), `${filename}-booking-poster.png`);
      } else {
        downloadBlob(await canvasPdf(target), `${filename}-booking-poster.pdf`);
      }
    } catch {
      setRenderError(t("The poster download could not be created. Please try again."));
    } finally {
      setDownloading(null);
    }
  }

  return (
    <div className="mt-4 border-t pt-4">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h4 className="text-sm font-semibold">Booking poster</h4>
          <p className="text-xs text-muted-foreground">A4 portrait · 300 DPI preview</p>
        </div>
        {rendering && <span role="status" className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><LoaderCircle className="size-3.5 animate-spin" />Preparing preview</span>}
      </div>
      {info.isError && <ErrorState error={info.error} onRetry={() => void info.refetch()} />}
      {renderError && <p role="alert" className="mb-3 text-sm text-destructive">{renderError}</p>}
      <div className="mx-auto max-w-[420px] overflow-hidden rounded-lg border bg-white shadow-sm">
        <canvas ref={canvas} aria-label={`${turf.name} booking poster preview`} className="block h-auto w-full" />
      </div>
      {!published && <p className="mt-2 text-xs text-amber-700">Publish the booking page and save settings before printing its poster.</p>}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" size="sm" variant="outline" disabled={rendering || !info.data || !published || Boolean(renderError) || downloading !== null} onClick={() => void download("png")}>
          {downloading === "png" ? <LoaderCircle className="animate-spin" /> : <Download />} Download Poster (PNG)
        </Button>
        <Button type="button" size="sm" variant="outline" disabled={rendering || !info.data || !published || Boolean(renderError) || downloading !== null} onClick={() => void download("pdf")}>
          {downloading === "pdf" ? <LoaderCircle className="animate-spin" /> : <Download />} Download Poster (PDF)
        </Button>
      </div>
    </div>
  );
}
