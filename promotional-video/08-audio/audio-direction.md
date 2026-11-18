# Audio direction

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
| 0:00–0:20 | 1. Hook — where's the pitch? | Music starts with a filtered pulse (−18 dB), crowd ambience low; one bass hit on «মাঠ কোথায়?». |
| 0:20–0:38 | 2. Introducing TurfBari | Music opens up to full beat at the logo (−14 dB under VO). Logo whoosh + soft ball bounce SFX. |
| 0:38–1:08 | 3. Public turf discovery | Soft UI clicks on each filter; light «tick» per card reveal (−24 dB). |
| 1:08–1:38 | 4. Turf details and QR booking | QR scan «bip» + short rising synth; tap sounds on slots; a gentle «ding» on Request sent. |
| 1:38–2:10 | 5. Turf Owner Dashboard | Music steady; subtle keyboard/typing SFX under the booking form; click on the 10% chip. |
| 2:10–2:35 | 6. Manager Dashboard | Small «lock» click on the view-only shot. VO slightly warmer on «নিয়ন্ত্রণ থাকে আপনার». |
| 2:35–3:00 | 7. Payments, reports and insights | Cash-register «ka-ching» is too loud for this brand — use a soft coin chime (−22 dB). Paper-swoosh on the export. |
| 3:00–3:18 | 8. The overall benefit | Music builds; crowd cheer swells under the last line, then drops for the CTA. |
| 3:18–3:35 | 9. Final branding and call to action | Music resolves on the tagline; final logo sting (single bass + shimmer). Silence for the last 0.5 s. |

This folder holds the direction only; add the licensed music file and the recorded VO here before editing.
