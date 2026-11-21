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
const DARK = "#073c31";
const LIME = "#bef264";
const MINT = "#d1fae5";

type PosterInfo = { booking_url: string; website_url: string };

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

function roundedRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, radius: number) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, radius);
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

  ctx.fillStyle = "#f5f8f3";
  ctx.fillRect(0, 0, WIDTH, HEIGHT);
  const header = ctx.createLinearGradient(0, 0, WIDTH, 1050);
  header.addColorStop(0, DARK);
  header.addColorStop(1, GREEN);
  ctx.fillStyle = header;
  ctx.fillRect(0, 0, WIDTH, 1010);
  ctx.fillStyle = LIME;
  ctx.fillRect(0, 1000, WIDTH, 14);

  const center = WIDTH / 2;
  const logoSize = 278;
  const logoX = center - logoSize / 2;
  const logoY = 122;
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,.22)";
  ctx.shadowBlur = 32;
  ctx.shadowOffsetY = 12;
  ctx.fillStyle = "#ffffff";
  ctx.beginPath();
  ctx.arc(center, logoY + logoSize / 2, logoSize / 2 + 14, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  ctx.save();
  ctx.beginPath();
  ctx.arc(center, logoY + logoSize / 2, logoSize / 2, 0, Math.PI * 2);
  ctx.clip();
  if (turfLogo) {
    const scale = Math.max(logoSize / turfLogo.width, logoSize / turfLogo.height);
    const w = turfLogo.width * scale;
    const h = turfLogo.height * scale;
    ctx.drawImage(turfLogo, center - w / 2, logoY + logoSize / 2 - h / 2, w, h);
  } else {
    ctx.fillStyle = "#e9f5ea";
    ctx.fillRect(logoX, logoY, logoSize, logoSize);
    const initials = turf.name.trim().split(/\s+/).slice(0, 2).map((part) => part[0] ?? "").join("");
    ctx.fillStyle = GREEN;
    ctx.font = "700 112px 'Hind Siliguri', 'Noto Sans Bengali', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(initials, center, logoY + logoSize / 2 + 8, logoSize - 36);
  }
  ctx.restore();

  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  const nameMaxWidth = 2110;
  let nameSize = 104;
  let nameLines: string[] = [];
  do {
    ctx.font = `700 ${nameSize}px 'Hind Siliguri', 'Noto Sans Bengali', sans-serif`;
    nameLines = wrappedLines(ctx, turf.name, nameMaxWidth);
    if (nameLines.length <= 2) break;
    nameSize -= 4;
  } while (nameSize > 64);
  ctx.fillStyle = "#ffffff";
  let y = 500;
  for (const line of nameLines.slice(0, 2)) {
    ctx.fillText(line, center, y, nameMaxWidth);
    y += nameSize * 1.08;
  }
  y += 12;
  if (turf.address.trim()) {
    ctx.font = "500 48px 'Hind Siliguri', 'Noto Sans Bengali', sans-serif";
    ctx.fillStyle = MINT;
    const addressLines = wrappedLines(ctx, turf.address, 2000).slice(0, 3);
    for (const line of addressLines) {
      ctx.fillText(line, center, y, 2000);
      y += 62;
    }
  }
  if (turf.public_phone.trim()) {
    y += 10;
    ctx.fillStyle = LIME;
    ctx.font = "700 54px Inter, Arial, sans-serif";
    ctx.fillText(turf.public_phone, center, y, 2000);
  }

  const instruction = language === "bn" ? "স্লট বুক করতে QR কোড স্ক্যান করুন" : "SCAN TO BOOK YOUR SLOT";
  ctx.fillStyle = GREEN;
  ctx.font = language === "bn"
    ? "700 66px 'Hind Siliguri', 'Noto Sans Bengali', sans-serif"
    : "700 58px Inter, Arial, sans-serif";
  ctx.fillText(instruction, center, 1110, 2100);

  const box = 1570;
  const boxX = center - box / 2;
  const boxY = 1190;
  ctx.save();
  ctx.shadowColor = "rgba(6,78,59,.12)";
  ctx.shadowBlur = 34;
  ctx.shadowOffsetY = 14;
  roundedRect(ctx, boxX, boxY, box, box, 34);
  ctx.fillStyle = "#ffffff";
  ctx.fill();
  ctx.restore();
  ctx.strokeStyle = "#d4e3d7";
  ctx.lineWidth = 4;
  roundedRect(ctx, boxX, boxY, box, box, 34);
  ctx.stroke();
  const qrSize = 1400;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(qr, center - qrSize / 2, boxY + (box - qrSize) / 2, qrSize, qrSize);
  ctx.imageSmoothingEnabled = true;

  ctx.fillStyle = LIME;
  roundedRect(ctx, center - 116, 2865, 232, 12, 6);
  ctx.fill();
  const markSize = 124;
  ctx.drawImage(brandMark, center - 382, 2935, markSize, markSize);
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillStyle = GREEN;
  ctx.font = "800 84px Inter, Arial, sans-serif";
  ctx.fillText("TURFBARI", center - 226, 2997);
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = "#43564b";
  ctx.font = "500 48px Inter, Arial, sans-serif";
  ctx.fillText(info.website_url, center, 3240, 2140);
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function markPngAs300Dpi(blob: Blob): Promise<Blob> {
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
