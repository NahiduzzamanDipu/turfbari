# TurfBari — Bengali promo film (spec)

GOAL:    A Bangladeshi footballer or turf owner finishes wanting to open turfbari.com — players to find a pitch, owners to list theirs.
OUTPUT:  HyperFrames, 1920 x 1080, 30 fps, MP4 H.264.
TIME:    170.0 s x 30 = 5100 frames. Clock = the voiceover (assets/voiceover.mp3, 167.08 s); 2.9 s end-card hold after it.
         No music bed or SFX in this cut: no music/SFX source is available on this machine (see README note).

LOOK:    Medium = the real TurfBari product. Every UI pixel is a real screenshot from 02-real-app-screenshots.
         Ground: the brand pitch-line field (03-reference-images/_illustrations/brand.png, #0B5A3F→#0E6B4C with 2 px lines at 12%).
         Cinematic beats: the floodlit-pitch illustrations (night, goal, ball) from the package.
         Ink #FFFFFF on ground, #0B1D13 on light. One accent: lime #B6F259 — highlighted words, title blocks, the "?" in the hook.
         Emerald #006040 = highlighted word inside a lime block.
         Display (Latin): Barlow Condensed ExtraBold (the app's display face) — wordmark, URL. Bengali: Hind Siliguri Bold/SemiBold.
         Big titles 96 px Hind Bold, line-height 1.25 (8.9% of frame height). Title blocks 54 px. Captions 50 px SemiBold.
         Browser window: radius 22 px, 44 px chrome, shadow 0 50px 120px rgba(0,0,0,.50). Phone: 457x956 bezel, radius 64 px.
OBJECTS: the browser window (three dots + turfbari.com), a phone with real mobile screens, the QR code, the ledger cards
         (paper #FAF6EA, 1.5° tilt, ink #1B1B1B), the cursor (white arrow, 1.5 px ink outline, 62 px tall).
MOTION:  Camera push / pan: 0.7–0.9 s power2.inOut, zoom 1.25–2.2x on the control the voice names, then held while it is read.
         Arrivals expo.out 0.5–0.6 s; exits power3.in, 45% shorter. Title words: blur 6→0 + opacity, 0.14 s, 0.07 s apart.
         Title blocks: clip-path wipe left→right 0.35 s expo.out. Phone screen swaps: 0.25 s crossfade with 8 px blur.
         Transitions (5 kinds): whip (0.3 s, 20 px blur), zoom-through (scale 1→1.6 + blur, 0.3 s power3.in), settle
         (incoming 1.06→1, 0.5 s), dip cut (outgoing −40% for 0.2 s), colour flood (lime, 0.4 s power2.inOut).
CAPTIONS: Bengali, from the approved script, timed to the voice by forced alignment (tools/align.py, pauses + speaking rate).
         Groups of ≤5 words, break at । ? — , and pauses ≥150 ms. Bottom-centred, 96 px from the bottom, scrim rgba(7,18,13,.78)
         sized to the text. Spoken word turns from 55% to 100% white (karaoke); at most one key word per group in lime,
         popping 1→1.12 on its word.
SHOTS:   Nine chapters on the voice's paragraph starts: 0 hook · 15.76 TurfBari · 31.17 discovery · 53.5 details + QR ·
         81.16 owner · 107.62 manager · 126.76 payments + reports · 146.04 benefits · 159.68 CTA + end card.
         Each sentence names a screen; the camera pushes into exactly that control while it is said (tools/build.py SHOTS).
BANNED:  black void; glow/bloom/particles; purple/blue gradients; glass cards; logo docked in a corner; three cards in a row;
         title over a dimmed screenshot; text moving while read; floating/breathing loops; click rings; invented UI or numbers;
         Admin/Super-Admin screens.
QA:      0.5 hook title · 3.2 "মাঠ কোথায়?" · 14.8 ledger cards · 18.5 logo · 24 split · 36.8 distance badges · 64 QR ·
         72 phone form · 84 KPI pan · 96 discount · 120 sidebar compare · 128 payments · 141 chart · 145 export click ·
         158 ball title · 168 end card. Captions legible on every one, never covering a title block.
