# Editing guide — TurfBari Bengali promo

## Technical spec
| Setting | Value |
|---|---|
| Resolution | 1920 × 1080 (16:9) |
| Frame rate | 30 fps |
| Duration | 3:35 (target 3:30–3:40) |
| Export | MP4, H.264 High, 16–20 Mbps VBR 2-pass, AAC 320 kbps 48 kHz |
| Colour | Rec.709, sRGB screenshots untouched |

Works the same in **CapCut Desktop**, **DaVinci Resolve** and **Premiere Pro**; tool-specific notes are at the end.

## Timeline
| Time | Scene | Title | On-screen Bengali text | Transition out |
|---|---|---|---|---|
| 0:00–0:20 | 1 | Hook — where's the pitch? | দল রেডি। মাঠ কোথায়? / খাতা • ফোনকল • বাকির হিসাব | Whip-pan blur into a lime light-sweep that reveals the logo (Scene 2). |
| 0:20–0:38 | 2 | Introducing TurfBari | টার্ফবাড়ি / প্রতিটি টার্ফের ঠিকানা / খেলোয়াড় • মালিক • ম্যানেজার | Zoom-through the search bar into the Explore page. |
| 0:38–1:08 | 3 | Public turf discovery | অ্যাকাউন্ট ছাড়াই টার্ফ খুঁজুন / কাছের টার্ফ আগে — দূরত্বসহ / জেলা • এলাকা • নাম দিয়ে সার্চ | Card-expand: the Green Arena card scales up into its turf page. |
| 1:08–1:38 | 4 | Turf details and QR booking | ছবি • সুবিধা • খোলার সময় • ভাড়া / প্রতিটি টার্ফের নিজস্ব QR কোড / রিকোয়েস্ট পাঠান → টার্ফ কনফার্ম করবে | Match-cut: the «Pending» badge on the player's phone becomes the pending-requests banner on the owner dashboard. |
| 1:38–2:10 | 5 | Turf Owner Dashboard | মালিকের ড্যাশবোর্ড / এক বোর্ডে সব স্লট / ডিসকাউন্ট ও অগ্রিমসহ বুকিং / মাঠ • সময় • ভাড়া • কাস্টমার | Slide the sidebar: the owner sidebar morphs into the shorter manager sidebar. |
| 2:10–2:35 | 6 | Manager Dashboard | ম্যানেজারের আলাদা লগইন / বুকিং • কনফার্ম • পেমেন্ট • কাস্টমার / ভাড়া, খরচ, রিপোর্ট — শুধু মালিকের হাতে | Push transition upward into the payments panel. |
| 2:35–3:00 | 7 | Payments, reports and insights | পরিশোধ • বাকি • পেমেন্টের মাধ্যম / আদায় • খরচ • নিট আয় / এক ক্লিকে এক্সেল | Pull back from the screen to a cinematic shot (VID-06 owner smiling at laptop). |
| 3:00–3:18 | 8 | The overall benefit | খেলোয়াড় — সহজ খোঁজা, সহজ রিকোয়েস্ট / মালিক — গোছানো ব্যবসা / ম্যানেজার — স্পষ্ট দায়িত্ব | Flash to white-lime then cut to the brand background. |
| 3:18–3:35 | 9 | Final branding and call to action | আপনার টার্ফ যুক্ত করুন / টার্ফ খুঁজুন / টার্ফবাড়ি — প্রতিটি টার্ফের ঠিকানা / turfbari.com | Fade to black (1 s). |

Full shot lists with the exact screenshot for each beat: `06-script/scene-by-scene-script.md`.

## Voiceover pace check (generated)
| Scene | Length | Bengali characters | Chars / second |
|---|---|---|---|
| 1 | 20 s | 210 | 10.5 |
| 2 | 18 s | 232 | 12.9 |
| 3 | 30 s | 322 | 10.7 |
| 4 | 30 s | 421 | 14.0 |
| 5 | 32 s | 370 | 11.6 |
| 6 | 25 s | 274 | 11.0 |
| 7 | 25 s | 260 | 10.4 |
| 8 | 18 s | 197 | 10.9 |
| 9 | 17 s | 168 | 9.9 |

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
