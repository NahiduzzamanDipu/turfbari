"""Build the TurfBari promo-video production package from production_data.py.

    python build_package.py frames   # writes 07-storyboard/frames.json (then run render-frames.mjs)
    python build_package.py docs     # scripts, SRT, storyboard, prompts, audio, editing guide, README, PDF html
"""

import json
import re
import sys
from pathlib import Path

import production_data as D

PKG = Path(__file__).resolve().parent.parent
BOM = "﻿"


def w(rel: str, text: str, bom: bool = False):
    path = PKG / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((BOM if bom else "") + text, encoding="utf-8", newline="\n")
    print("wrote", rel)


def tc(sec: float) -> str:
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}"


def srt_time(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ------------------------------------------------------------------ subtitles
MAX_CUE = 80  # code points per cue (Bengali vowel signs count separately); shown on up to 2 lines
LINE = 42  # wrap a cue onto two lines above this many code points


def split_cues(sentence: str) -> list[str]:
    """Break a sentence into readable cues at natural pauses (— ; , ।)."""
    if len(sentence) <= MAX_CUE:
        return [sentence]
    parts = re.split(r"(?<=[—;,])\s*", sentence)
    cues, cur = [], ""
    for part in parts:
        if cur and len(cur) + len(part) + 1 > MAX_CUE:
            cues.append(cur.strip())
            cur = part
        else:
            cur = f"{cur} {part}" if cur and not cur.endswith("—") else cur + part
    if cur.strip():
        cues.append(cur.strip())
    return cues


def two_lines(text: str) -> str:
    """Balance a long cue over two lines, breaking at the space nearest the middle."""
    if len(text) <= LINE:
        return text
    mid = len(text) // 2
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    if not spaces:
        return text
    cut = min(spaces, key=lambda i: abs(i - mid))
    return text[:cut] + "\n" + text[cut + 1 :]


def build_cues():
    cues, report = [], []
    for sc in D.SCENES:
        lines = [c for s in sc["vo"] for c in split_cues(s)]
        lead, tail = 0.35, 0.35
        avail = (sc["end"] - sc["start"]) - lead - tail
        total = sum(len(x) for x in lines)
        t = sc["start"] + lead
        floor = 0.9  # every cue stays readable for at least this long
        spare = avail - floor * len(lines)
        for line in lines:
            dur = floor + spare * len(line) / total
            cues.append((t, t + dur - 0.06, two_lines(line)))
            t += dur
        chars = sum(len(s) for s in sc["vo"])
        report.append((sc["id"], sc["end"] - sc["start"], chars, chars / (sc["end"] - sc["start"])))
    return cues, report


# ------------------------------------------------------------------ helpers
def md_img(rel: str, alt: str = "") -> str:
    return f"![{alt}](../{rel})"


def screen_list(text: str) -> str:
    if text in ("—", ""):
        return "—"
    return "<br>".join(f"`{x.strip()}`" for x in text.split("|"))


def frames_json():
    frames = {}
    for fid, f in D.FRAMES.items():
        f = dict(f)
        if f["layout"] == "cta":
            f["url"] = D.URL
        frames[fid] = f
    w("07-storyboard/frames.json", json.dumps(frames, ensure_ascii=False, indent=2))


# ------------------------------------------------------------------ documents
def scripts(cues):
    full = "\n\n".join(" ".join(sc["vo"]) for sc in D.SCENES)
    w("06-script/full-bengali-voiceover.txt", full + "\n")
    w(
        "06-script/full-bengali-voiceover.md",
        f"# {D.BRAND_BN} — সম্পূর্ণ বাংলা ভয়েসওভার\n\n"
        f"> দৈর্ঘ্য প্রায় {tc(D.TOTAL_SECONDS)} মিনিট। ভয়েস আর্টিস্ট বা AI ভয়েস জেনারেটরে সরাসরি দেওয়ার জন্য। "
        f"প্রতিটি অনুচ্ছেদের পরে ০.৫–০.৮ সেকেন্ড বিরতি দিন। ব্র্যান্ডের নাম সবসময় «টার্ফবাড়ি» উচ্চারণ করুন (টার্ফ-বা-ড়ি)।\n\n"
        + full
        + "\n",
    )
    out = [f"# {D.BRAND_BN} — দৃশ্যভিত্তিক স্ক্রিপ্ট (Scene-by-scene script)\n",
           f"Total: **{tc(D.TOTAL_SECONDS)}** · 1920×1080 · 30 fps · Bengali voiceover\n"]
    for sc in D.SCENES:
        out += [
            f"\n## দৃশ্য {sc['id']} — {sc['title_bn']}  \n*{sc['title_en']}*\n",
            "| | |", "|---|---|",
            f"| **সময় (Timestamp)** | {tc(sc['start'])} – {tc(sc['end'])} |",
            f"| **দৈর্ঘ্য (Duration)** | {sc['end'] - sc['start']} সেকেন্ড |",
            f"| **ভয়েসওভার** | {' '.join(sc['vo'])} |",
            f"| **অন-স্ক্রিন বাংলা লেখা** | {' / '.join('«' + t + '»' for t in sc['onscreen'])} |",
            f"| **ট্রানজিশন** | {sc['transition']} |",
            f"| **অডিও** | {sc['audio']} |",
            "",
            "**Shot list (visual direction and required UI screenshot)**",
            "",
            "| Time | Visual direction | Real screenshot / asset |",
            "|---|---|---|",
            *[f"| {t} | {v} | {screen_list(s)} |" for t, v, s in sc["shots"]],
            "",
            "Reference frames: " + " ".join(f"[{f}](../03-reference-images/scene-{f[1:3]}/{f}.png)" for f in sc["frames"]),
            "",
        ]
    w("06-script/scene-by-scene-script.md", "\n".join(out))

    srt = []
    for i, (a, b, line) in enumerate(cues, 1):
        srt.append(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{line}\n")
    w("06-script/bengali-subtitles.srt", "\n".join(srt), bom=True)


def storyboard():
    out = [f"# Storyboard — {D.BRAND} Bengali promo ({tc(D.TOTAL_SECONDS)})\n",
           "Every UI pixel in these frames is a real screenshot from the running app. Cinematic frames are illustrated "
           "placeholders for the AI footage in `05-ai-video-prompts/`.\n"]
    for sc in D.SCENES:
        out.append(f"\n## {sc['id']}. {sc['title_en']} — {tc(sc['start'])}–{tc(sc['end'])}\n")
        out.append(f"**VO:** {' '.join(sc['vo'])}\n")
        for fid in sc["frames"]:
            f = D.FRAMES[fid]
            out.append(f"**{fid}** — {f.get('chip') or f.get('title', '')}\n\n{md_img(f'03-reference-images/scene-{fid[1:3]}/{fid}.png', fid)}\n")
        out.append(f"*Transition:* {sc['transition']}  \n*Audio:* {sc['audio']}\n")
    w("07-storyboard/storyboard.md", "\n".join(out))

    tiles = "".join(
        f'<figure><img src="../03-reference-images/scene-{fid[1:3]}/{fid}.png"><figcaption><b>{fid} · {tc(sc["start"])}–{tc(sc["end"])}</b> {sc["title_en"]}<br><span>{D.FRAMES[fid].get("sub", "")}</span></figcaption></figure>'
        for sc in D.SCENES for fid in sc["frames"]
    )
    w("07-storyboard/storyboard-sheet.html", f"""<!doctype html><html lang="bn"><head><meta charset="utf-8"><title>Storyboard</title>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@800&family=Inter:wght@400;600&family=Hind+Siliguri:wght@500&display=swap" rel="stylesheet">
<style>body{{margin:0;padding:48px;background:#f7fbf8;font-family:Inter,'Hind Siliguri',sans-serif;color:#0b1d13;width:1824px}}
h1{{font-family:'Barlow Condensed';font-size:56px;text-transform:uppercase;margin:0 0 24px}}
main{{display:grid;grid-template-columns:repeat(4,1fr);gap:22px}} figure{{margin:0;background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 6px 18px rgb(0 0 0/.06)}}
img{{width:100%;display:block}} figcaption{{padding:10px 12px;font-size:14px;line-height:1.4}} span{{font-family:'Hind Siliguri';color:#526259}}</style></head>
<body><h1>TurfBari Bengali promo — storyboard ({tc(D.TOTAL_SECONDS)})</h1><main>{tiles}</main></body></html>""")


def prompts():
    idx = ["# AI image prompts\n", "Use for cinematic support visuals only. **Never** generate the app UI, the logo or a QR code — those come from `01-brand-assets/` and `02-real-app-screenshots/`.\n",
           "| ID | Scene | Visual |", "|---|---|---|"]
    for p in D.IMAGE_PROMPTS:
        idx.append(f"| [{p['id']}]({p['id']}.md) | {p['scene']} | {p['title']} |")
        one_line = (
            f"{p['subject']}. {p['environment']}. {p['composition']}. Camera: {p['camera']}. Lighting: {p['lighting']}. "
            f"Mood: {p['mood']}. Style: {p['style']}. {D.PALETTE_TEXT} {p.get('extra', '')} Aspect ratio {p['ratio']}."
        ).replace("  ", " ")
        w(f"04-ai-image-prompts/{p['id']}.md", f"""# {p['id']} — {p['title']}

**Scene:** {p['scene']} · **Purpose:** {p['title']} (cinematic support visual, not UI)

| Field | Direction |
|---|---|
| Main subject | {p['subject']} |
| Environment | {p['environment']} |
| Composition | {p['composition']} |
| Camera angle / lens | {p['camera']} |
| Lighting | {p['lighting']} |
| Background | {p['environment']} |
| Colour palette | {D.PALETTE_TEXT} |
| Mood | {p['mood']} |
| Visual style | {p['style']} |
| Aspect ratio | {p['ratio']} |
| Notes | {p.get('extra', '—')} |

## Ready-to-paste prompt (ChatGPT image / Imagen / Midjourney)

```
{one_line}
```

Midjourney suffix: `--ar 16:9 --style raw --v 6.1`

## Negative prompt

```
{D.NEGATIVE_IMAGE}
```
""")
    w("04-ai-image-prompts/README.md", "\n".join(idx) + "\n")

    vidx = ["# AI video prompts\n", "All clips: 16:9, 24–30 fps, 1080p or higher. Generate 2–3 takes each and pick the cleanest. Add the logo, UI and QR in the edit, never in generation.\n",
            "| ID | Scene | Clip | Duration |", "|---|---|---|---|"]
    for v in D.VIDEO_PROMPTS:
        vidx.append(f"| [{v['id']}]({v['id']}.md) | {v['scene']} | {v['title']} | {v['duration']} |")
        line = (
            f"{v['duration']} cinematic shot, 16:9. {v['subject']}. Camera: {v['camera']}. Environment: {v['environment']}. "
            f"Lighting: {v['lighting']}. Colour grade: {v['grade']}; TurfBari palette emerald #065F46 and lime #BEF264. "
            f"Consistent look with the other TurfBari clips: urban Bangladeshi turf at night, realistic people, natural motion. {v.get('extra', '')}"
        ).replace("  ", " ")
        w(f"05-ai-video-prompts/{v['id']}.md", f"""# {v['id']} — {v['title']}

| Field | Direction |
|---|---|
| Scene | {v['scene']} |
| Duration | {v['duration']} |
| Aspect ratio | 16:9 |
| Camera movement | {v['camera']} |
| Subject movement | {v['subject']} |
| Lighting | {v['lighting']} |
| Environment | {v['environment']} |
| Colour grading | {v['grade']} |
| Brand palette | Emerald #065F46 / #006040, lime #BEF264, ink #0B1D13 |
| Consistency | Same city, same turf style, same grade across VID-01…07 |
| Notes | {v.get('extra', '—')} |

## Prompt (Veo / Kling / Runway / Sora)

```
{line}
```

## Negative prompt

```
{D.NEGATIVE_VIDEO}
```
""")
    w("05-ai-video-prompts/README.md", "\n".join(vidx) + "\n")


def audio():
    rows = "\n".join(f"| {tc(sc['start'])}–{tc(sc['end'])} | {sc['id']}. {sc['title_en']} | {sc['audio']} |" for sc in D.SCENES)
    w("08-audio/audio-direction.md", f"""# Audio direction

## Voiceover
- **Voice:** warm, confident Bangladeshi Bengali (standard Dhaka accent), age 25–35, male or female. Friendly and modern, not a news-reader tone.
- **Pace:** about 13–15 Bengali characters per second; the script is timed for that (see `09-editing-guide`). Slow down for the tagline «টার্ফবাড়ি—প্রতিটি টার্ফের ঠিকানা».
- **Brand name:** always «টার্ফবাড়ি» (Turf-Bari), stress on «বাড়ি».
- **English product words** (Dashboard, Booking, QR, Excel) are said naturally, Bengali-style.
- **Recording:** 48 kHz / 24-bit WAV, dry (no reverb), −3 dBFS peaks. Record each scene as a separate take with 1 s room tone before and after.
- **AI voice option:** Google Cloud TTS `bn-IN-Wavenet` / ElevenLabs multilingual with a Bengali voice; paste `06-script/full-bengali-voiceover.txt`, then fix any mispronounced brand names by spelling them phonetically.

## Music
- Modern, uplifting sports-tech: 100–115 BPM, light percussion, synth plucks, a subtle stadium-crowd pad. No vocals.
- Royalty-free sources to search: YouTube Audio Library, Pixabay Music, Artlist or Epidemic Sound (check licence for paid ads).
- Structure: filtered intro (0:00–0:20) → full beat at the logo (0:20) → steady bed (0:38–2:55) → build (3:00) → resolve on the tagline (3:30).

## Sound effects (soft, never louder than the voice)
| Moment | SFX |
|---|---|
| Logo reveal | short whoosh + soft ball bounce |
| UI clicks, filter changes | subtle tap (−24 dB) |
| QR scan | short «bip» + rising synth |
| Request sent | gentle «ding» |
| Payments | soft coin chime (−22 dB) |
| Excel export | paper swoosh |
| Goal celebration | crowd swell (−18 dB) |
| End card | bass hit + shimmer |

## Mix targets
- Voice −16 LUFS integrated for online platforms (−14 LUFS for YouTube is fine); music ducked to −14 dB under voice, −8 dB in gaps.
- True peak ≤ −1 dBTP. High-pass the voice at 80 Hz, light de-ess, 2:1 compression.

## Cue sheet
| Time | Scene | Music / SFX |
|---|---|---|
{rows}

This folder holds the direction only; add the licensed music file and the recorded VO here before editing.
""")


def editing_guide(report):
    timeline = "\n".join(
        f"| {tc(sc['start'])}–{tc(sc['end'])} | {sc['id']} | {sc['title_en']} | {' / '.join(sc['onscreen'])} | {sc['transition']} |" for sc in D.SCENES
    )
    pace = "\n".join(f"| {sid} | {dur} s | {chars} | {rate:.1f} |" for sid, dur, chars, rate in report)
    w("09-editing-guide/editing-guide.md", f"""# Editing guide — TurfBari Bengali promo

## Technical spec
| Setting | Value |
|---|---|
| Resolution | 1920 × 1080 (16:9) |
| Frame rate | 30 fps |
| Duration | {tc(D.TOTAL_SECONDS)} (target 3:30–3:40) |
| Export | MP4, H.264 High, 16–20 Mbps VBR 2-pass, AAC 320 kbps 48 kHz |
| Colour | Rec.709, sRGB screenshots untouched |

Works the same in **CapCut Desktop**, **DaVinci Resolve** and **Premiere Pro**; tool-specific notes are at the end.

## Timeline
| Time | Scene | Title | On-screen Bengali text | Transition out |
|---|---|---|---|---|
{timeline}

Full shot lists with the exact screenshot for each beat: `06-script/scene-by-scene-script.md`.

## Voiceover pace check (generated)
| Scene | Length | Bengali characters | Chars / second |
|---|---|---|---|
{pace}

10–15 chars/s is a natural Bengali ad pace (the hook, manager and CTA scenes are deliberately slower to leave room for music and visuals). If your recorded VO runs long, trim pauses first, then extend the scene by up to 2 s; keep the total under 3:45.

## Brand rules (from the real app)
- **Logo:** use only `01-brand-assets/logo/*`. Never redraw, recolour or stretch it. Minimum clear space = the height of the roof.
- **Colours:** emerald `#006040` / tile `#065F46`, lime `#B6F259`–`#BEF264`, ink `#0B1D13`, mist `#F7FBF8` (`01-brand-assets/colors/palette.md`).
- **Type:** headlines Barlow Condensed 800 uppercase (English) / Hind Siliguri 700 (Bengali); body Inter / Hind Siliguri 500.
- **UI:** show screenshots as they are. Do not edit numbers, names or layouts, and **never show the Super Admin area**.
- Surfaces: soft glass cards (white 10% fill, 1 px white 22% border, 18 px blur) and the emerald gradient used in `03-reference-images`.

## Animation recipes
| Effect | How |
|---|---|
| **Logo reveal** | Roof: trim-path stroke 0→100% (0.6 s, ease-out). Ball: scale 0→110→100% with a 6 px drop/bounce (0.4 s). Wordmark: mask-slide from behind the mark (0.5 s). Import the SVG (`turfbari-mark.svg`) to keep it vector. |
| **Smooth UI zoom** | Scale 100→112% over the shot length, ease-in-out; anchor on the element being described. Never exceed 130% (keep text sharp; screenshots are 1920 px). |
| **Cursor interaction** | Use a clean macOS-style pointer PNG, 2–3 moves per shot max, 0.35 s eased moves, a 12 px lime ring pulse on click. |
| **Dashboard scrolling** | Use `*-full.png` / `*full-page.png` tall screenshots and keyframe Y position; 250–350 px/s. |
| **Location search** | Pulse the «Showing turfs nearest to you» chip (lime ring), then pop the «700 m away» badge (scale 100→118→100%). |
| **Turf card reveal** | Stagger cards 80 ms apart: opacity 0→1, Y +24 px → 0, 0.35 s. |
| **QR scanning** | Corner-pin the real QR SVG onto IMG-04 / VID-05; lime scan line top→bottom 0.6 s; then an iris/zoom into the phone screenshot. |
| **Booking flow** | Phone mock-ups (see frames s04-c/d). Tap ripple on the chosen slots; slide between the four mobile screenshots (0.3 s push). |
| **Chart animation** | Mask-wipe the real chart left→right (1.2 s). Do not animate numbers to different values. |
| **Bengali kinetic type** | Hind Siliguri 700, 96–128 px, word-by-word pop (scale 85→100%, 0.18 s each), lime colour on the key word. Max 6 words on screen. |
| **Focus highlight** | Lime 5 px rounded outline + 30% emerald dim outside (see frames with focus boxes). |
| **Final CTA** | Logo lock-up settles (0.5 s), tagline fades up, two pills pop in 0.15 s apart, URL types on. Hold 4 s. |

Keep it premium: one transition style per scene, no spins, no glitches, no star wipes.

## Subtitles
- Import `06-script/bengali-subtitles.srt` (UTF-8 with BOM; same wording as the voiceover).
- Style: Hind Siliguri 500, 42 px, white, black box at 60% opacity, 12 px radius; bottom-centre, 46 px from the bottom; max 2 lines.
- After recording, nudge cues to the real VO waveform (±0.3 s is normal).
- Subtitles stay above lower-third chips; they never cover a highlighted UI element — move the zoom instead.

## Audio mix
See `08-audio/audio-direction.md`: voice −16 LUFS, music ducked −14 dB under speech, true peak ≤ −1 dBTP.

## Tool notes
- **CapCut Desktop:** Text → Import SRT; Keyframes for zoom; “Ease in-out” curves; export 1080p 30 fps “Higher” bitrate.
- **DaVinci Resolve:** Fusion for the logo trim-path; Subtitles track → Import SRT; Fairlight “Auto ducking”; Deliver: H.264 Master, 1080p 30.
- **Premiere Pro:** Essential Graphics for kinetic text; Captions → Import SRT; Essential Sound “Ducking”; export H.264 “Match Source – High bitrate”.

## Before export — checklist
- [ ] No Super Admin / admin screens anywhere (all UI is from `02-real-app-screenshots/`, which contains none).
- [ ] Screenshots unedited; demo data either kept as is or re-captured with your own turf's real data (`tools/capture.mjs`).
- [ ] QR in the video re-captured from the production domain (the current one points to the local dev address).
- [ ] URL on the end card is the live domain.
- [ ] Subtitles match the final recorded voiceover word for word.
""")


def audit_md() -> str:
    def rows(key):
        return "\n".join(f"| {a} | {b} |" for a, b in D.AUDIT[key])

    return f"""### ✅ Implemented — promoted in the video
| Feature | What exists |
|---|---|
{rows('implemented')}

### ⚠️ Partial
| Feature | Status |
|---|---|
{rows('partial')}

### ❌ Not implemented — kept out of the script
| Feature | Status |
|---|---|
{rows('missing')}
"""


def readme(report):
    w("README.md", f"""# TurfBari — Bengali promotional video production package

Everything needed to produce a ~{tc(D.TOTAL_SECONDS)} Bengali promo for the **public website, turf owners, managers and football teams**.
No Super Admin / admin screen, feature or wording appears anywhere in this package.

> **Brand name:** the brief says “TURFOS”; the product was renamed **TurfBari** (টার্ফবাড়ি) on 18 Nov 2026 with a new logo.
> This package uses the real, current brand. Tagline: **«{D.TAGLINE_BN}»**. URL used on the end card: `{D.URL}` (not registered yet — register it or change `tools/production_data.py` and rebuild).

## Start here
1. Read `06-script/full-bengali-voiceover.md` and record the voiceover (direction in `08-audio/`).
2. Follow `09-editing-guide/editing-guide.md` with the storyboard `07-storyboard/storyboard.md`.
3. Real UI: `02-real-app-screenshots/`. Cinematic footage: generate from `04-ai-image-prompts/` and `05-ai-video-prompts/`.
4. Everything in one document: `TurfBari_Bengali_Promotional_Video_Guide.pdf`.

## Structure
```
promotional-video/
├── 01-brand-assets/        logo (SVG + PNG: on light, on dark, transparent dark-ink and light-ink), colours, typography
├── 02-real-app-screenshots/ real screens, 1920×1080 desktop and 390×844 mobile
│   ├── public-homepage/ turf-discovery/ turf-details/ qr-booking/
│   ├── owner-dashboard/ booking-management/ customer-management/
│   ├── field-and-pricing/ payment-management/ reports/
│   └── manager-dashboard/  (manager's own login only — never owner/admin screens)
├── 03-reference-images/    scene-01 … scene-09 keyframes + _illustrations/
├── 04-ai-image-prompts/    IMG-01 … IMG-10
├── 05-ai-video-prompts/    VID-01 … VID-07
├── 06-script/              full-bengali-voiceover.md/.txt, scene-by-scene-script.md, bengali-subtitles.srt
├── 07-storyboard/          storyboard.md, storyboard-sheet.png, frames.json
├── 08-audio/               audio-direction.md (voice, music, SFX, mix, cue sheet)
├── 09-editing-guide/       editing-guide.md
├── 10-pdf/                 source HTML + images for the PDF
├── tools/                  scripts that produced all of the above (re-runnable)
└── TurfBari_Bengali_Promotional_Video_Guide.pdf
```

## Feature audit (from the real code and running app, 18 Nov 2026)
{audit_md()}

## About the data in the screenshots
The screenshots come from the real application running locally with its **demo data** (demo turfs, teams and amounts). They are real screens, not mock-ups, but the numbers are demo numbers.
Before publishing, either keep them clearly as a product demo or re-capture with your own turf's data:

```bash
node promotional-video/tools/capture.mjs        # all groups; or: public | owner | manager
```
The turf photos on the demo turfs are TurfBari-palette illustrations (`tools/scenes.html`), uploaded through the app's normal photo upload. Replace them with real turf photos for the final cut.

## Rebuilding
```bash
cd promotional-video/tools
python build_package.py frames && node render-frames.mjs   # reference frames
python build_package.py docs && node render-docs.mjs        # docs, storyboard sheet, PDF
node render-brand.mjs                                      # logo, palette, type sheets
```
Requires the dev servers (backend 8011, frontend 5175) for screenshots, Node 22+ and Chrome.

## Final quality checklist
- [x] Duration {tc(D.TOTAL_SECONDS)} (3–4 min) · 9 scenes
- [x] 100% Bengali voiceover; English only for product terms
- [x] Hook in the first 5 seconds («দল রেডি, বুট রেডি, মনটাও রেডি। কিন্তু মাঠ কোথায়?»)
- [x] Public website, location-based discovery (district, area, near-me), turf details, gallery
- [x] QR booking explained accurately (request → turf confirms; status lookup)
- [x] Owner dashboard, booking, customers, fields, pricing, payments, reports
- [x] Manager dashboard as its own scene, real manager screenshots, honest permissions
- [x] Only implemented features promoted; missing ones listed above and kept out
- [x] Real screenshots, real logo, exact brand colours
- [x] Bengali SRT with the same wording as the voiceover
- [x] AI image + video prompts with negatives (no fake UI, logos or QR)
- [x] Final CTA (find a turf / list your turf / URL)
- [x] No Super Admin or admin content anywhere
""")


def pdf_html(cues, report):
    """Single HTML document printed to PDF by render-docs.mjs. Images are JPEG previews in 10-pdf/img."""
    from PIL import Image

    img_dir = PKG / "10-pdf" / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    def thumb(rel: str, width=1280) -> str:
        src = PKG / rel
        out = img_dir / (rel.replace("/", "__").rsplit(".", 1)[0] + ".jpg")
        if src.suffix.lower() == ".svg":
            return "../" + rel
        with Image.open(src) as im:
            im = im.convert("RGB")
            if im.width > width:
                im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
            im.save(out, "JPEG", quality=82, optimize=True)
        return "img/" + out.name

    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    import production_data as P

    pal = json.loads((PKG / "01-brand-assets/colors/palette.json").read_text(encoding="utf-8"))
    swatches = "".join(
        f'<div class="sw"><i style="background:{c["hex"]}"></i><b>{esc(c["name"])}</b><br>{c["hex"]} · {esc(c["oklch"])}</div>' for c in pal
    )
    scenes_html = ""
    for sc in P.SCENES:
        shots = "".join(f"<tr><td>{t}</td><td>{esc(v)}</td><td class='mono'>{esc(s).replace(' | ', '<br>')}</td></tr>" for t, v, s in sc["shots"])
        frames = "".join(f'<figure><img src="{thumb(f"03-reference-images/scene-{fid[1:3]}/{fid}.png", 960)}"><figcaption>{fid}</figcaption></figure>' for fid in sc["frames"])
        scenes_html += f"""<section class="scene"><h2>দৃশ্য {sc['id']} · {esc(sc['title_bn'])} <small>{tc(sc['start'])}–{tc(sc['end'])} · {sc['end'] - sc['start']} s · {esc(sc['title_en'])}</small></h2>
<p class="vo">{esc(' '.join(sc['vo']))}</p>
<p><b>অন-স্ক্রিন লেখা:</b> {' / '.join('«' + esc(t) + '»' for t in sc['onscreen'])}</p>
<div class="frames">{frames}</div>
<table><tr><th>Time</th><th>Visual direction</th><th>Real screenshot / asset</th></tr>{shots}</table>
<p><b>Transition:</b> {esc(sc['transition'])}<br><b>Audio:</b> {esc(sc['audio'])}</p></section>"""

    shots_gallery = ""
    for folder in sorted(p for p in (PKG / "02-real-app-screenshots").iterdir() if p.is_dir()):
        figs = "".join(
            f'<figure><img src="{thumb(str(f.relative_to(PKG)).replace(chr(92), "/"), 900)}"><figcaption>{f.name}</figcaption></figure>'
            for f in sorted(folder.glob("*.png"))
        )
        shots_gallery += f"<h3>{folder.name}</h3><div class='grid'>{figs}</div>"

    img_prompts = "".join(
        f"<div class='prompt'><h3>{p['id']} · {esc(p['title'])} <small>scene {p['scene']}</small></h3><p>{esc(p['subject'])}. {esc(p['environment'])}. {esc(p['composition'])}. Camera: {esc(p['camera'])}. Lighting: {esc(p['lighting'])}. Mood: {esc(p['mood'])}. Style: {esc(p['style'])}. {esc(P.PALETTE_TEXT)} {esc(p.get('extra', ''))} Aspect ratio {p['ratio']}.</p></div>"
        for p in P.IMAGE_PROMPTS
    )
    vid_prompts = "".join(
        f"<div class='prompt'><h3>{v['id']} · {esc(v['title'])} <small>scene {v['scene']} · {v['duration']}</small></h3><p><b>Camera:</b> {esc(v['camera'])}. <b>Subject:</b> {esc(v['subject'])}. <b>Lighting:</b> {esc(v['lighting'])}. <b>Environment:</b> {esc(v['environment'])}. <b>Grade:</b> {esc(v['grade'])}. {esc(v.get('extra', ''))}</p></div>"
        for v in P.VIDEO_PROMPTS
    )
    audit = "".join(
        f"<h3>{title}</h3><table>{''.join(f'<tr><td><b>{esc(a)}</b></td><td>{esc(b)}</td></tr>' for a, b in P.AUDIT[key])}</table>"
        for key, title in (("implemented", "✅ Implemented — promoted"), ("partial", "⚠️ Partial"), ("missing", "❌ Not implemented — kept out"))
    )
    srt_rows = "".join(f"<tr><td class='mono'>{srt_time(a)}</td><td>{esc(t).replace(chr(10), '<br>')}</td></tr>" for a, _, t in cues)
    full_vo = "".join(f"<p>{esc(' '.join(sc['vo']))}</p>" for sc in P.SCENES)
    pace = "".join(f"<tr><td>{s}</td><td>{d} s</td><td>{c}</td><td>{r:.1f}</td></tr>" for s, d, c, r in report)
    checklist = "".join(
        f"<li>{x}</li>"
        for x in [
            "Voiceover recorded and approved (Bengali, ~3:35)", "Music licensed for advertising use", "AI clips generated (VID-01…07) and graded to the palette",
            "Real QR re-captured from the production domain", "Screenshots re-captured with your own data, or kept as clearly labelled demo",
            "End-card URL is the live domain", "SRT re-timed to the final voiceover", "Brand check: logo untouched, colours exact",
            "No Super Admin / admin content anywhere", "Exported 1920×1080, 30 fps, H.264, −16 LUFS",
        ]
    )
    html = f"""<!doctype html><html lang="bn"><head><meta charset="utf-8"><title>TurfBari Bengali Promotional Video Guide</title>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;800&family=Inter:wght@400;600;700&family=Hind+Siliguri:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
@page {{ size: A4; margin: 14mm 13mm; }}
body {{ font-family: Inter, 'Hind Siliguri', 'Noto Sans Bengali', 'Nirmala UI', sans-serif; color: #0b1d13; font-size: 10.5pt; line-height: 1.5; }}
h1, h2, h3 {{ font-family: 'Barlow Condensed', 'Hind Siliguri', sans-serif; text-transform: none; color: #0b1d13; }}
h1 {{ font-size: 30pt; margin: 0 0 6pt; }} h2 {{ font-size: 18pt; margin: 18pt 0 6pt; border-bottom: 2pt solid #b6f259; padding-bottom: 3pt; }}
h2 small, h3 small {{ font-family: Inter; font-size: 9pt; color: #526259; font-weight: 400; }}
h3 {{ font-size: 13pt; margin: 12pt 0 4pt; }}
.cover {{ height: 255mm; display: flex; flex-direction: column; justify-content: center; background: linear-gradient(135deg, #022c22, #065f46); color: #fff; padding: 0 18mm; border-radius: 6mm; break-after: page; }}
.cover h1 {{ color: #fff; font-size: 40pt; }} .cover p {{ font-size: 13pt; }} .cover img {{ width: 120mm; margin-bottom: 10mm; }} .lime {{ color: #bef264; }}
.page {{ break-before: page; }} .scene {{ break-inside: auto; }} .vo {{ font-family: 'Hind Siliguri'; font-size: 12.5pt; background: #e4f3ea; padding: 8pt 10pt; border-radius: 6pt; }}
table {{ width: 100%; border-collapse: collapse; margin: 6pt 0; font-size: 9pt; }} th, td {{ border: 0.5pt solid #cfdcd4; padding: 4pt 5pt; vertical-align: top; text-align: left; }} th {{ background: #f0f7f2; }}
.mono {{ font-family: Consolas, monospace; font-size: 8pt; word-break: break-all; }}
.frames {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6pt; }} figure {{ margin: 0; break-inside: avoid; }} figure img {{ width: 100%; border-radius: 4pt; border: 0.5pt solid #cfdcd4; }}
figcaption {{ font-size: 8pt; color: #526259; }} .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 6pt; }}
.sw {{ display: inline-block; width: 31%; margin: 0 1% 8pt 0; font-size: 8.5pt; vertical-align: top; }} .sw i {{ display: block; height: 16mm; border-radius: 4pt; margin-bottom: 3pt; border: 0.5pt solid #cfdcd4; }}
.prompt {{ break-inside: avoid; border-left: 3pt solid #b6f259; padding-left: 8pt; margin-bottom: 8pt; }} .prompt p {{ margin: 2pt 0; font-size: 9.5pt; }}
.fullvo p {{ font-family: 'Hind Siliguri'; font-size: 13pt; line-height: 1.75; }}
ul.check li {{ list-style: '☐  '; margin: 3pt 0; }}
</style></head><body>
<div class="cover"><img src="../01-brand-assets/logo/turfbari-logo-horizontal-light-transparent.png"><h1>Bengali Promotional Video <span class="lime">Production Guide</span></h1>
<p>টার্ফবাড়ি — {esc(P.TAGLINE_BN)}</p><p>Duration {tc(P.TOTAL_SECONDS)} · 1920×1080 · 30 fps · 100% Bengali voiceover<br>Audience: football teams, turf owners and managers · No admin content</p>
<p style="font-size:10pt;opacity:.8">Brief received as “TURFOS”; the product is now TurfBari — this guide uses the current brand.<br>Generated 18 Nov 2026 from the running application.</p></div>

<h2>1. Brand identity</h2>
<p>Logo: a বাড়ি (home) roof sheltering a football — “every turf's home”. Use only the files in <code>01-brand-assets/logo/</code>.</p>
<div class="frames"><figure><img src="{thumb('01-brand-assets/logo/turfbari-logo-horizontal-on-light.png', 1200)}"></figure><figure><img src="{thumb('01-brand-assets/logo/turfbari-logo-horizontal-on-dark.png', 1200)}"></figure></div>
<h3>Colours (exact app tokens)</h3>{swatches}
<h3>Typography</h3><figure><img src="{thumb('01-brand-assets/typography/turfbari-typography.png', 1400)}"></figure>

<div class="page"></div><h2>2. Feature audit — what the video may promote</h2>{audit}

<div class="page"></div><h2>3. সম্পূর্ণ বাংলা ভয়েসওভার (Full Bengali voiceover)</h2><div class="fullvo">{full_vo}</div>
<h3>Pace check</h3><table><tr><th>Scene</th><th>Length</th><th>Characters</th><th>Chars/s</th></tr>{pace}</table>

<div class="page"></div><h2>4. Storyboard and scene timing</h2>{scenes_html}

<div class="page"></div><h2>5. Real application screenshots</h2><p>Captured from the running app (public site, owner and manager workspaces). Demo data. No admin screens.</p>{shots_gallery}

<div class="page"></div><h2>6. AI image prompts</h2><p><b>Negative prompt for all images:</b> {esc(P.NEGATIVE_IMAGE)}</p>{img_prompts}
<h2>7. AI video prompts</h2><p><b>Negative prompt for all clips:</b> {esc(P.NEGATIVE_VIDEO)}</p>{vid_prompts}

<div class="page"></div><h2>8. Editing instructions</h2>
<p>Full guide: <code>09-editing-guide/editing-guide.md</code>. Key rules:</p>
<ul><li>1920×1080, 30 fps, H.264 MP4, AAC 320 kbps; voice −16 LUFS, music ducked −14 dB, true peak ≤ −1 dBTP.</li>
<li>Logo reveal: roof trim-path 0.6 s → ball drop-bounce 0.4 s → wordmark mask-slide 0.5 s.</li>
<li>UI zoom 100→112% eased, max 130%; cursor moves 0.35 s with a lime click ring; card reveals staggered 80 ms.</li>
<li>QR: corner-pin the real QR onto the standee plate; lime scan line 0.6 s; iris into the phone screenshot.</li>
<li>Charts: mask-wipe the real chart; never animate numbers to other values.</li>
<li>Bengali kinetic type: Hind Siliguri 700, 96–128 px, word-by-word pops, lime key word, max 6 words.</li>
<li>Subtitles: import the SRT; Hind Siliguri 500 42 px white on 60% black box, bottom-centre.</li>
<li>One transition style per scene; no spins or glitch effects.</li></ul>
<h3>Bengali subtitles (SRT, start times)</h3><table><tr><th>Start</th><th>Text</th></tr>{srt_rows}</table>

<div class="page"></div><h2>9. Production checklist</h2><ul class="check">{checklist}</ul>
</body></html>"""
    w("10-pdf/guide.html", html)


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "docs"
    if what == "frames":
        frames_json()
        return
    cues, report = build_cues()
    scripts(cues)
    storyboard()
    prompts()
    audio()
    editing_guide(report)
    readme(report)
    pdf_html(cues, report)
    for sid, dur, chars, rate in report:
        flag = "" if 9.5 <= rate <= 15.5 else "  <-- check pace"
        print(f"scene {sid}: {dur:>3}s {chars:>4} chars {rate:5.1f}/s{flag}")
    longest = max(len(x) for _, _, t in cues for x in t.split("\n"))
    shortest = round(min(b - a for a, b, _ in cues), 2)
    print("cues:", len(cues), "longest line:", longest, "shortest cue (s):", shortest)


if __name__ == "__main__":
    main()
