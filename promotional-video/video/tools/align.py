"""Align the known Bengali script to voiceover.mp3 without speech recognition.

Speech segments come from ffmpeg silencedetect (assets/silences.txt). Words are assigned to
segments by dynamic programming: each segment should be spoken at the overall average rate
(characters per second), and segment edges prefer punctuation. Inside a segment, word times are
spread by character count. Output: assets/words.json [{id, text, start, end, para}].
"""

import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SCRIPT = HERE.parent / "06-script" / "full-bengali-voiceover.txt"
DURATION = 167.079

silences = []
for line in (HERE / "assets" / "silences.txt").read_text().split():
    if "-" in line and "(" not in line:
        a, b = line.split("-")
        silences.append((float(a), float(b)))

# speech segments between silences
segments, t = [], 0.0
for a, b in silences:
    if a - t > 0.05:
        segments.append((t, a))
    t = b
if DURATION - t > 0.05:
    segments.append((t, DURATION))
# trim leading silence of the file: detect first sound roughly at 0.1 s (no leading silence reported)

paras = [p.strip() for p in SCRIPT.read_text(encoding="utf-8").split("\n") if p.strip()]
words = []  # (text, para_index)
for pi, p in enumerate(paras):
    for w in p.split():
        # split "খেলা—সব" style em-dash joins into separate words, keeping the dash on the first
        parts = re.split(r"(?<=—)", w)
        for part in parts:
            if part:
                words.append((part, pi))

def weight(w: str) -> float:
    letters = re.sub(r"[^\wঀ-৿]", "", w)
    return max(1, len(letters)) + 1.2  # +gap between words


def end_bonus(w: str) -> float:
    if re.search(r"[।?!]$", w):
        return 0.0
    if re.search(r"[,—;:]$", w):
        return 0.35
    return 1.6  # pause inside a phrase: possible but discouraged


W = len(words)
cum = [0.0]
for w, _ in words:
    cum.append(cum[-1] + weight(w))
total_speech = sum(b - a for a, b in segments)
rate = cum[-1] / total_speech
S = len(segments)
INF = float("inf")
MAXW = 40
dp = [[INF] * (W + 1) for _ in range(S + 1)]
back = [[-1] * (W + 1) for _ in range(S + 1)]
dp[0][0] = 0.0
for i in range(1, S + 1):
    a, b = segments[i - 1]
    dur = b - a
    for j in range(1, W + 1):
        best, arg = INF, -1
        for k in range(max(0, j - MAXW), j):
            if dp[i - 1][k] == INF:
                continue
            chars = cum[j] - cum[k]
            r = chars / dur / rate
            cost = dp[i - 1][k] + (math.log(r)) ** 2 * 4 + end_bonus(words[j - 1][0])
            if cost < best:
                best, arg = cost, k
        dp[i][j], back[i][j] = best, arg
if dp[S][W] == INF:
    sys.exit("alignment failed")

bounds, j = [], W
for i in range(S, 0, -1):
    k = back[i][j]
    bounds.append((k, j))
    j = k
bounds.reverse()

out = []
for (k, j), (a, b) in zip(bounds, segments):
    span = cum[j] - cum[k]
    for n in range(k, j):
        s = a + (cum[n] - cum[k]) / span * (b - a)
        e = a + (cum[n + 1] - cum[k]) / span * (b - a)
        out.append({"id": f"w{n}", "text": words[n][0], "start": round(s, 3), "end": round(e - 0.04, 3), "para": words[n][1]})

(HERE / "assets" / "words.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"segments={S} words={W} rate={rate:.2f} cost={dp[S][W]:.2f}")
for (k, j), (a, b) in zip(bounds, segments):
    r = (cum[j] - cum[k]) / (b - a) / rate
    print(f"{a:6.2f}-{b:6.2f} r={r:4.2f} | " + " ".join(w for w, _ in words[k:j]))
starts = {}
for w in out:
    starts.setdefault(w["para"], w["start"])
print("para starts", {p: round(s, 2) for p, s in starts.items()})
