# Review — TurfBari Bengali promo (170 s)

Checked: `hyperframes check` passes (0 errors). 36 snapshot frames read at the SPEC's QA moments plus fixes.

Fixed after the first look
- Caption words merged around highlighted words ("আরম্যানেজার?") → word spacing restored, key pop 1.12 → 1.08.
- "আনন্দটাই বাড়ে" sat on the white ball → title moved above the ball.
- Phones ran under the caption band → moved right / up; split-screen phone shrunk so its label stays clear.
- Caption hard-kill set `visibility` on the clip (113 lint errors) → moved to the inner box.
- First frame was empty (thumbnail) → the hook illustration is on screen at 0 s.

Known limits
- Captions are timed by forced alignment of the approved script to the voice's pauses (no speech recogniser was available);
  each phrase starts on its real pause, word highlights inside a phrase are interpolated by character count.
- No music bed or sound effects: no music/SFX source on this machine. Add a track as `<audio id="music" … data-volume="0.14">`
  in index.html (or drop one in the desktop app).
- Ledger cards, the menu comparison (real labels) and the end-card buttons are rebuilt graphics; every other UI pixel is a
  real TurfBari screenshot. No Admin screens appear.

Delivered render: ../TurfBari_Promo_Bengali_1080p.mp4 — 170.0 s, 1920x1080, 30 fps, H.264 + AAC, 52 MB.
Audio measured (not listened to): voiceover normalised to -17.2 LUFS integrated, -1.7 dB peak (was -25.1 LUFS).
The original voiceover is kept as assets/voiceover-original.mp3.

## v2 (cursor-driven walkthrough) — delivered ../TurfBari_Promo_Bengali_1080p_v2.mp4
- Built by tools/build2.py: each chapter is one browser window; the cursor clicks real nav items, buttons, rows and a
  free slot, each click opens the next real screenshot, the URL bar follows, long pages scroll, camera follows the cursor.
- Chapter cards (lime sweep) at Players / Owner / Payments; captions bolder with a lime marker sweep on the key word.
- Fixed in review: QR scan bar visible from the chapter start (fromTo immediateRender) → explicit set/tween/set;
  motion blur smeared camera glides → camera opted out (data-motion-blur="off"), blur kept for panels and cursor;
  search URL said "mirpur" while the screen shows "Uttara" → corrected.
- check: 0 errors. Loudness measured -14.2 LUFS, peak -1.6 dB. 170.0 s, 1080p30, H.264/AAC.
- SEO: MP4 metadata (title, keywords, description, genre, language, copyright) + 9 named chapters (tools/finalize.py).
  Subtitles ship as TurfBari_Promo_Bengali.bn.srt (an embedded MP4 subtitle track is always switched on in players).
