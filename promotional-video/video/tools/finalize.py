"""Add the invisible SEO layer to the rendered promo (no re-encode of the picture).

- MP4 metadata (title, artist, genre, date, language, copyright, comment, description, synopsis, keywords)
- named chapter markers (one per story chapter)
The Bengali subtitles are NOT embedded: MP4 always enables its first subtitle track, so players such as VLC
would show it. They ship as the sidecar assets/turfbari-promo.bn.srt for upload instead.

Usage:  python tools/finalize.py <rendered.mp4> <output.mp4>
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TITLE = "TurfBari — বাংলাদেশে ফুটবল টার্ফ খুঁজুন ও বুক করুন | Turf Booking & Turf Management Software"
KEYWORDS = [
    "TurfBari", "turfbari.com", "টার্ফবাড়ি", "টার্ফ বুকিং", "অনলাইন টার্ফ বুকিং", "ফুটবল টার্ফ", "ফুটবল মাঠ ভাড়া",
    "কাছের টার্ফ", "ঢাকার টার্ফ", "টার্ফ ম্যানেজমেন্ট সফটওয়্যার", "টার্ফ মালিক", "টার্ফ ম্যানেজার", "বুকিং রিকোয়েস্ট",
    "QR কোড বুকিং", "বিকাশ নগদ পেমেন্ট", "turf booking Bangladesh", "football turf Dhaka", "turf near me",
    "online turf booking", "futsal booking Bangladesh", "turf management software", "turf booking app",
    "sports facility booking", "turf owner dashboard", "QR code booking", "Mirpur turf", "Gulshan turf",
    "Uttara turf", "Dhanmondi turf", "Chattogram turf", "Sylhet turf", "5 a side football", "7 a side football",
    "rooftop turf Dhaka", "indoor futsal Dhaka",
]
DESCRIPTION = (
    "টার্ফবাড়ি (TurfBari) — প্রতিটি টার্ফের ঠিকানা। অ্যাকাউন্ট ছাড়াই কাছের ফুটবল টার্ফ খুঁজুন, জেলা ও এলাকা দিয়ে সার্চ করুন, "
    "ছবি, সুবিধা, খোলার সময় আর ভাড়া দেখুন, QR কোড স্ক্যান করে বুকিং রিকোয়েস্ট পাঠান। টার্ফ মালিক ও ম্যানেজারদের জন্য "
    "বুকিং, পেমেন্ট (ক্যাশ, বিকাশ, নগদ), ডিসকাউন্ট, কাস্টমার, রিপোর্ট আর এক্সেল এক্সপোর্ট — এক ড্যাশবোর্ডে। "
    "TurfBari is a football turf discovery, online booking and turf management platform for Bangladesh: find turfs "
    "near you in Dhaka, Chattogram and Sylhet, book with a QR code, and run your turf business with an owner and "
    "manager dashboard. turfbari.com"
)
CHAPTERS = [
    (0.0, "মাঠ কোথায়? — Finding a turf"),
    (15.76, "টার্ফবাড়ি — Introducing TurfBari"),
    (31.17, "টার্ফ খুঁজুন — Turf discovery"),
    (53.5, "টার্ফ পেজ ও QR বুকিং — Turf page & QR booking"),
    (81.16, "মালিকের ড্যাশবোর্ড — Owner dashboard"),
    (107.62, "ম্যানেজার — Manager workspace"),
    (126.76, "পেমেন্ট ও রিপোর্ট — Payments & reports"),
    (146.04, "সবার জন্য সহজ — Benefits"),
    (159.68, "আজই যুক্ত হোন — Join TurfBari"),
]
TOTAL = 170.0


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
        "-metadata", "album=TurfBari — প্রতিটি টার্ফের ঠিকানা",
        "-metadata", "genre=Sports Technology / Football",
        "-metadata", "date=2026",
        "-metadata", "copyright=© 2026 TurfBari — turfbari.com",
        "-metadata", f"comment={DESCRIPTION} | Keywords: {kw}",
        "-metadata", f"description={DESCRIPTION}",
        "-metadata", f"synopsis={DESCRIPTION}",
        "-metadata", f"keywords={kw}",
        "-metadata", "language=ben",
        "-metadata:s:a:0", "language=ben",
        "-movflags", "+faststart",
        out,
    ]
    subprocess.run(cmd, check=True)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
