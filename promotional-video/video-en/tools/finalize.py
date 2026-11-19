"""Add the invisible SEO layer to the rendered promo (no re-encode of the picture).

- MP4 metadata (title, artist, genre, date, language, copyright, comment, description, synopsis, keywords)
- named chapter markers (one per story chapter)
The English subtitles are NOT embedded: MP4 always enables its first subtitle track, so players such as VLC
would show it. They ship as the sidecar assets/turfbari-promo.en.srt for upload instead.

Usage:  python tools/finalize.py <rendered.mp4> <output.mp4>
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TITLE = "TurfBari — Find & Book Football Turfs in Bangladesh | Turf Booking & Turf Management Platform"
KEYWORDS = [
    "TurfBari", "turf booking", "football turf booking", "online turf booking", "turf booking Bangladesh",
    "football turf Dhaka", "turf near me", "futsal booking", "turf management software", "sports facility booking",
    "booking management system", "turf owner dashboard", "QR code booking", "bKash Nagad payments", "SaaS",
    "Django", "React", "web application", "product demo", "full-stack project", "Bangladesh startup",
    "Mirpur turf", "Gulshan turf", "Uttara turf", "Dhanmondi turf", "5 a side football", "7 a side football",
]
DESCRIPTION = (
    "TurfBari — The Address of Every Turf. A football turf discovery, online booking and turf management platform "
    "for Bangladesh. Players find the nearest turfs, see photos, facilities, opening hours and slot prices, and send "
    "booking requests without an account or by scanning a turf's QR code. Owners and managers run bookings, "
    "discounts and advances, cash / bKash / Nagad payments, customers, reports and one-click Excel export from one "
    "dashboard. Demo: turfbari.onrender.com"
)
CHAPTERS = [
    (0.0, "Where is the field?"),
    (24.25, "Introducing TurfBari"),
    (40.15, "Find a turf"),
    (65.1, "Turf page & QR booking"),
    (98.59, "Owner dashboard"),
    (128.51, "Managers"),
    (154.37, "Payments & reports"),
    (179.8, "Better for everyone"),
    (199.4, "Join TurfBari"),
]
TOTAL = 214.34


def ffmeta() -> Path:
    def esc(v: str) -> str:
        return v.replace("\\", "\\\\").replace("=", "\\=").replace(";", "\\;").replace("#", "\\#").replace("\n", "\\\n")

    lines = [";FFMETADATA1"]
    for i, (t, name) in enumerate(CHAPTERS):
        end = CHAPTERS[i + 1][0] if i + 1 < len(CHAPTERS) else TOTAL
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(t * 1000)}", f"END={int(end * 1000)}", f"title={esc(name)}"]
    path = ROOT / "assets" / "chapters.ffmeta"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(src: str, out: str):
    meta = ffmeta()
    kw = ", ".join(KEYWORDS)
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-i", src, "-f", "ffmetadata", "-i", str(meta),
        "-map", "0:v", "-map", "0:a", "-map_chapters", "1",
        "-c:v", "copy", "-c:a", "copy",
        "-metadata", f"title={TITLE}",
        "-metadata", "artist=TurfBari",
        "-metadata", "album_artist=TurfBari",
        "-metadata", "album=TurfBari — The Address of Every Turf",
        "-metadata", "genre=Sports Technology / Product Demo",
        "-metadata", "date=2026",
        "-metadata", "copyright=© 2026 TurfBari — turfbari.onrender.com",
        "-metadata", f"comment={DESCRIPTION} | Keywords: {kw}",
        "-metadata", f"description={DESCRIPTION}",
        "-metadata", f"synopsis={DESCRIPTION}",
        "-metadata", f"keywords={kw}",
        "-metadata", "language=eng",
        "-metadata:s:a:0", "language=eng",
        "-movflags", "+faststart",
        out,
    ]
    subprocess.run(cmd, check=True)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
