"""TurfBari promo — English edition (LinkedIn), built from the v2 cursor-driven walkthrough.

The Bengali v2 shot list (tools/build2.py) is reused as-is: every time in it is on the Bengali voice clock.
WARP maps that clock onto the English voiceover (anchors = the same sentence in both scripts), so every
cursor click, page change, camera move and label lands on the English line that names it. All on-screen
Bengali text is translated through TR; the build fails if any Bengali is left in the output.

Run (from tools/):  python align.py && python build_en.py
"""

import copy
import json
import re
from html import escape
from pathlib import Path

import build as v1
import build2 as v2
from build import LIME, f, rich

ROOT = Path(__file__).resolve().parents[1]
WORDS = json.loads((ROOT / "assets" / "words.json").read_text(encoding="utf-8"))
VOICE_END = WORDS[-1]["end"] + 0.04
BN = re.compile(r"[ঀ-৿]")


# ------------------------------------------------------------------------------------ clock warp
def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


_cursor = [0]


def at(phrase, plus=0.0, nth=1):
    """English start time of the nth occurrence of `phrase` (searching forward from the previous anchor)."""
    toks = [norm(t) for t in phrase.split()]
    i = _cursor[0]
    seen = 0
    while i < len(WORDS):
        if all(i + k < len(WORDS) and norm(WORDS[i + k]["text"]) == toks[k] for k in range(len(toks))):
            seen += 1
            if seen == nth:
                _cursor[0] = i + 1
                return WORDS[i]["start"] + plus
        i += 1
    raise SystemExit(f"anchor not found: {phrase}")


ANCHORS = [  # (Bengali clock, English clock)
    (0.0, 0.0), (2.90, at("But where")), (4.15, at("Finding a turf")), (6.29, at("checking the rental")),
    (7.24, at("figuring out")), (8.50, at("can take so")), (10.64, at("Meanwhile,")), (12.10, at("managing notebooks")),
    (13.25, at("handling one phone")), (14.45, at("outstanding payments.")), (15.76, at("To make things")),
    (19.08, at("A single platform")), (22.40, at("while turf owners")), (26.99, at("through an organized")),
    (28.62, at("TurfBari")), (29.48, at("Address of Every")), (31.17, at("You don't need")),
    (34.55, at("Simply allow")), (38.79, at("along with their")), (40.61, at("You can also select")),
    (42.80, at("or search by")), (44.93, at("Each turf card")), (46.33, at("whether it's indoor")),
    (47.78, at("the number of")), (50.31, at("all at a")), (51.21, at("No more calling")),
    (53.50, at("Once you visit")), (56.49, at("available facilities")), (57.25, at("field information")),
    (58.29, at("opening hours")), (60.76, at("With just one")), (63.69, at("Every turf also")),
    (66.09, at("Simply scan")), (69.09, at("Select your preferred")), (69.51, at("field, and available")),
    (71.71, at("enter your name")), (74.85, at("Once the turf")), (77.70, at("You can also check")),
    (81.16, at("Now, let's talk")), (82.72, at("The dashboard gives")), (84.53, at("today's collections")),
    (85.70, at("monthly revenue")), (87.97, at("outstanding payments.", 0.9)), (89.09, at("The Book a")),
    (91.65, at("booked, or")), (92.29, at("or waiting")), (94.86, at("If a team")),
    (97.81, at("including discounts")), (99.86, at("Manage your fields")), (100.24, at("opening hours,")),
    (101.55, at("peak-hour")), (103.41, at("and customer booking")), (105.10, at("all in one")),
    (106.60, at("without depending")), (107.62, at("And what about")), (108.57, at("Owners can add")),
    (113.06, at("Managers can handle")), (114.83, at("confirm booking requests")), (116.47, at("record payments,")),
    (118.91, at("However, changing")), (120.03, at("managing expenses")), (120.38, at("viewing reports")),
    (122.02, at("remain exclusively")), (124.04, at("Responsibilities are")), (124.88, at("but control")),
    (126.76, at("For every booking")), (129.09, at("the amount already")), (131.64, at("cash,")),
    (132.10, at("bKash,")), (133.10, at("or Nagad,")), (134.74, at("every transaction")),
    (136.67, at("The reports section")), (138.28, at("expenses, and net")), (139.77, at("along with daily")),
    (141.51, at("booking statistics")), (143.30, at("Need a report?")), (146.04, at("For players,", nth=1)),
    (150.18, at("For owners,")), (153.46, at("For managers,")), (155.70, at("When the hassles")),
    (157.39, at("the joy")), (159.68, at("If you're a")), (160.64, at("add your turf")),
    (162.46, at("And if you")), (163.68, at("find the perfect")), (165.15, at("TurfBari")),
    (165.55, at("Address of Every")), (166.40, at("Making Every")), (167.08, VOICE_END),
]
for (a0, b0), (a1, b1) in zip(ANCHORS, ANCHORS[1:]):
    assert a1 > a0 and b1 > b0, f"anchor order broken near {a0} -> {a1}: {b0} -> {b1}"


def warp(t):
    for (a0, b0), (a1, b1) in zip(ANCHORS, ANCHORS[1:]):
        if t <= a1:
            return b0 + (t - a0) * (b1 - b0) / (a1 - a0) if t >= a0 else b0
    a, b = ANCHORS[-1]
    return b + (t - a)  # after the voice: real seconds


TOTAL = int(warp(v1.TOTAL) * 100) / 100  # end card holds as long as in the Bengali cut


# ------------------------------------------------------------------------------------ translations
TR = {
    # hook
    "দল রেডি, বুট রেডি": "Team ready.\nBoots ready.", "মাঠ *কোথায়?*": "But where's\nthe *field?*",
    "আজ রাতে সময় খালি?": "A free slot tonight?", "ভাড়া কত?": "What's the price?", "কাকে ফোন করবেন?": "Who do you call?",
    "আর টার্ফ মালিকের দিন কাটে…": "Meanwhile, turf owners juggle…",
    "খাতা": "Notebooks", "ফোনকল": "Phone calls", "বাকির হিসাব": "Unpaid dues",
    # intro
    "*খেলোয়াড়দের* জন্য": "For *players*", "*মালিক ও ম্যানেজারদের* জন্য": "For *owners & managers*",
    "সব এক প্ল্যাটফর্মে": "One organized platform", "প্রতিটি টার্ফের *ঠিকানা*": "The address of *every turf*",
    # players
    "*অ্যাকাউন্ট* লাগে না": "No *account* needed", "*কাছের* টার্ফ আগে": "*Nearest* turfs first",
    "পাশে লেখা — কত *দূরে*": "With the *distance*", "*জেলা* আর এলাকা": "Pick *district* & area",
    "টার্ফের *নাম* দিয়ে সার্চ": "Search by *name*", "*ছবি*": "*Photos*", "ইনডোর না *আউটডোর*": "Indoor or *outdoor*",
    "কয়টি মাঠ • শুরুর *ভাড়া*": "Fields • starting *price*", "দশ জায়গায় ফোন — *শেষ*": "No more *calling around*",
    "ছবির *গ্যালারি*": "Photo *gallery*", "সুবিধা • মাঠ • *খোলার সময়*": "Facilities • fields • *hours*",
    "প্রতিটি স্লটের *ভাড়া*": "Price for *every slot*", "ম্যাপে এক ট্যাপে *রাস্তা*": "*Directions* in one tap",
    "নিজস্ব *QR* কোড": "Its own *QR code*",
    "স্ক্যান করলেই *বুকিং পেজ*": "Scan to open\nthe *booking page*", "তারিখ • মাঠ • *খালি সময়*": "Date • field •\n*free slot*",
    "নাম আর *মোবাইল নম্বর*": "Name &\n*mobile number*", "*কনফার্ম* হলেই খেলা পাকা": "*Confirmed?*\nGame on!",
    "রেফারেন্স দিয়ে *স্ট্যাটাস*": "Track *status*\nanytime",
    "খেলোয়াড়দের *জন্য*": "For *players*", "টার্ফ *মালিকের* জন্য": "For turf *owners*", "পেমেন্ট আর *রিপোর্ট*": "Payments & *reports*",
    # owner
    "আজকের বুকিং • *আজকের আদায়*": "Today's bookings • *collections*", "মাসের আয় • মোট *বকেয়া*": "Monthly revenue • *dues*",
    "*বুক আ স্লট* বোর্ড": "The *Book a Slot* board", "খালি • বুকড • *অপেক্ষায়*": "Free • booked • *pending*",
    "ফোনের বুকিং — *কয়েক সেকেন্ডে*": "Phone bookings in *seconds*", "*ডিসকাউন্ট* আর অগ্রিমসহ": "With *discount* & advance",
    "*মাঠ*": "*Fields*", "*খোলার সময়*": "*Opening hours*", "পিক আওয়ার • *উইকেন্ড* ভাড়া": "Peak-hour • *weekend* pricing",
    "কাস্টমারের বুকিং *ইতিহাস*": "Customer booking *history*", "সবকিছু *গোছানো*": "All *organized*",
    # manager
    "আর *ম্যানেজার?*": "And *managers?*", "টিম পেজ থেকে *ম্যানেজার*": "Add managers from *Team*",
    "নিজের আলাদা *লগইন*": "Their own *login*", "প্রতিদিনের *বুকিং*": "Daily *bookings*", "রিকোয়েস্ট *কনফার্ম*": "*Confirm* requests",
    "*পেমেন্ট* রেকর্ড": "Record *payments*", "*কাস্টমার* সামলান": "Manage *customers*",
    "ভাড়া বদলানো • খরচ • রিপোর্ট • টিম": "Prices • expenses • reports • team", "শুধু *মালিকের* হাতে": "Stay with the *owner*",
    "কাজ ভাগ হয়,\n*নিয়ন্ত্রণ* থাকে আপনার": "Responsibilities shared,\n*control* stays with you",
    # money
    "মোট *ভাড়া*": "Total *rent*", "পরিশোধ আর *বাকি*": "Paid & *remaining*", "ক্যাশ • *বিকাশ* • নগদ": "Cash • *bKash* • Nagad",
    "বুকিংয়ের সঙ্গেই *রেকর্ড*": "Recorded with *the booking*", "আদায় • খরচ • *নিট আয়*": "Collections • expenses • *net income*",
    "দিনভিত্তিক আদায়ের *চার্ট*": "Daily collection *chart*", "কোন মাঠে কত *বুকিং*": "*Bookings* per field",
    "এক ক্লিকে *এক্সেল*": "*Excel* in one click",
    # benefits / cta
    "খেলোয়াড়দের জন্য\nসহজে টার্ফ *খোঁজা*": "Players:\n*hassle-free*\nbooking",
    "মালিকের জন্য *পরিষ্কার হিসাব*": "Owners: *transparent records*", "ম্যানেজারের *স্পষ্ট দায়িত্ব*": "Managers: *clear roles*",
    "মাঠের বাইরের ঝামেলা কমলে,": "Less hassle off the field,", "মাঠের ভেতরের\n*আনন্দটাই* বাড়ে": "more *joy*\non it.",
    "আজই আপনার টার্ফ *যুক্ত করুন*": "*Add your turf* today", "পরের ম্যাচের *মাঠ*": "Find your next *field*",
}
HTML_TR = {  # Bengali hard-coded inside the v1 shot builders
    'rich("প্রতিটি টার্ফের *ঠিকানা*")': None,  # handled by endcard override
    ">শুধু দেখা<": ">View only<", ">মালিক<": ">Owner<", ">ম্যানেজার<": ">Manager<",
}


def translate(obj):
    if isinstance(obj, str):
        if BN.search(obj):
            if obj not in TR:
                raise SystemExit(f"missing translation: {obj!r}")
            return TR[obj]
        return obj
    if isinstance(obj, list):
        return [translate(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(translate(x) for x in obj)
    if isinstance(obj, dict):
        return {k: translate(v) for k, v in obj.items()}
    return obj


# ------------------------------------------------------------------------------------ scene builder patches
def lt(self, t):
    return max(0.0, warp(t) - self.start)


def open_shot(self, s):
    self.z += 1
    d = warp(s["t1"]) - warp(s["t0"])
    self.html.append(
        f'<div id="{s["id"]}" class="clip shot" data-start="{f(self.lt(s["t0"]))}" data-duration="{f(d)}" '
        f'data-track-index="1" style="z-index:{self.z}"><div id="{s["id"]}-in" class="enter">'
    )


def chapter(self, s):
    sid = s["id"]
    d = warp(s["t1"]) - warp(s["t0"])
    self.z += 20
    self.html.append(
        f'<div id="{sid}" class="clip shot" data-start="{f(self.lt(s["t0"]))}" data-duration="{f(d)}" '
        f'data-track-index="2" style="z-index:{self.z}">'
        f'<div id="{sid}-panel" class="chpanel"><div class="kicker" id="{sid}-k">{escape(s["kicker"])}</div>'
        f'<div class="chtitle" id="{sid}-t">{rich(s["title"])}</div></div></div>'
    )
    t0 = self.lt(s["t0"])
    self.tw(f'tl.fromTo("#{sid}-panel", {{xPercent: -101}}, {{xPercent: 0, duration: 0.38, ease: "expo.out"}}, {f(t0)});')
    self.tw(f'tl.fromTo("#{sid}-k", {{opacity: 0, y: 12}}, {{opacity: 1, y: 0, duration: 0.3, ease: "power3.out"}}, {f(t0 + 0.18)});')
    self.words_in(f"#{sid}-t", s["t0"] + 0.22)
    self.tw(f'tl.to("#{sid}-panel", {{xPercent: 101, duration: 0.36, ease: "power3.in"}}, {f(t0 + d - 0.38)});')


def endcard(self, s):
    sid = s["id"]
    self.open_shot(s)
    self.html.append(
        f'<div class="lockup end" id="{sid}-lock"><img id="{sid}-mark" class="mark" src="assets/mark.png" alt="">'
        f'<div id="{sid}-word" class="wordmark">Turf<b>Bari</b></div></div>'
        f'<div id="{sid}-tag" class="big under2">{rich("The address of *every turf*")}</div>'
        f'<div id="{sid}-sub" class="sub">{rich("Making every game easier")}</div>'
        f'<div id="{sid}-ctas" class="ctas"><span class="btn solid">Find a turf</span><span class="btn ghost">List your turf</span></div>'
        f'<div id="{sid}-url" class="url">turfbari.onrender.com</div>'
    )
    self.html.append("</div>")
    self.tw(f'tl.fromTo("#{sid}-mark", {{scale: 0.3, rotation: -12, opacity: 0}}, {{scale: 1, rotation: 0, opacity: 1, duration: 0.7, ease: "back.out(1.6)"}}, {f(self.lt(165.15))});')
    self.tw(f'tl.fromTo("#{sid}-word", {{clipPath: "inset(0% 100% 0% 0%)", x: -30}}, {{clipPath: "inset(0% 0% 0% 0%)", x: 0, duration: 0.6, ease: "expo.out"}}, {f(self.lt(165.5))});')
    self.words_in(f"#{sid}-tag", 165.6)
    self.words_in(f"#{sid}-sub", 166.4)
    self.tw(f'tl.fromTo("#{sid}-ctas .btn", {{y: 30, opacity: 0}}, {{y: 0, opacity: 1, duration: 0.5, ease: "expo.out", stagger: 0.1}}, {f(self.lt(167.1))});')
    self.tw(f'tl.fromTo("#{sid}-url", {{opacity: 0}}, {{opacity: 1, duration: 0.4, ease: "power2.out"}}, {f(self.lt(167.5))});')
    self.close_tail(s)


v1.Scene.lt = lt
v1.Scene.open_shot = open_shot
v1.Scene.endcard = endcard
v2.WorldScene.chapter = chapter
v1.TOTAL = TOTAL

# Latin typography: Inter for text, Barlow Condensed for the wordmark/kickers/url
EN_CSS = """
#root { font-family: Inter, sans-serif; }
#root .big { font-weight: 900; letter-spacing: -0.02em; line-height: 1.08; }
#root .big.hero { width: 1100px; font-size: 104px; }
#root .big.top { font-size: 70px; }
#root .big.center { font-size: 118px; line-height: 1.05; }
#root .big.side-right, #root .big.side-left { font-size: 88px; width: 960px; }
#root .big.under { font-size: 64px; letter-spacing: -0.01em; }
#root .big.under2 { font-size: 76px; }
#root .tag2 .tx { font-weight: 800; font-size: 50px; letter-spacing: -0.01em; padding: 12px 30px 14px 24px; }
#root .tag { font-weight: 800; }
#root .chip { font-weight: 700; font-size: 46px; }
#root .card { font-weight: 900; font-size: 70px; letter-spacing: -0.02em; }
#root .label { font-weight: 800; font-size: 50px; letter-spacing: -0.01em; }
#root .chtitle { font-weight: 900; font-size: 140px; letter-spacing: -0.03em; line-height: 1.02; }
#root .sub { font-weight: 700; font-size: 48px; }
#root .btn { font-weight: 800; font-size: 42px; padding: 14px 40px 16px; }
#root .sbhead { font-weight: 800; font-size: 40px; }
#root .viewonly { font: 700 28px Inter, sans-serif; }
"""

KEYWORDS = [
    "field?", "TurfBari", "account", "nearest", "district", "search", "photos", "gallery", "map", "directions",
    "QR", "scan", "request", "confirms", "dashboard", "Slot", "discounts", "advance", "managers", "login",
    "control", "balance", "bKash", "reports", "net", "charts", "Excel", "joy", "Address", "notebooks",
    "outstanding", "price", "revenue", "payments", "owners", "players", "distances", "status", "Every",
    "available", "seconds", "pricing", "history", "Team", "authority", "paid", "transaction", "simple",
    "transparent", "responsibilities", "today", "perfect", "Easier", "glance", "tonight",
]


def is_key(word):
    w = norm(word)
    return any(norm(k) == w or (len(norm(k)) > 4 and w.startswith(norm(k))) for k in KEYWORDS)


# ------------------------------------------------------------------------------------ captions (English)
def caption_groups():
    groups, cur = [], []
    for i, w in enumerate(WORDS):
        cur.append(w)
        nxt = WORDS[i + 1] if i + 1 < len(WORDS) else None
        t = w["text"]
        chars = sum(len(x["text"]) + 1 for x in cur)
        brk = (
            nxt is None
            or re.search(r"[.?!]$", t)
            or (re.search(r"[,—–;:]$", t) and len(cur) >= 3)
            or chars >= 34
            or (nxt and nxt["start"] - w["end"] >= 0.18 and len(cur) >= 2)
            or (nxt and nxt["para"] != w["para"])
        )
        if brk:
            groups.append(cur)
            cur = []
    return groups


def build_captions():
    groups = caption_groups()
    html, js = [], []
    for gi, g in enumerate(groups):
        start = max(0.12, g[0]["start"] - 0.06)
        nxt_start = groups[gi + 1][0]["start"] - 0.06 if gi + 1 < len(groups) else TOTAL
        end = min(g[-1]["end"] + 0.3, nxt_start - 0.02)
        key_done, spans = False, []
        for wi, w in enumerate(g):
            k = not key_done and is_key(w["text"])
            key_done = key_done or k
            spans.append(f'<span id="cw{gi}-{wi}" class="cw{" key" if k else ""}">{escape(w["text"])}</span>')
            if k:
                js.append(f'tl.to("#cw{gi}-{wi}", {{color: "#10280B", backgroundSize: "100% 100%", duration: 0.22, ease: "power2.out"}}, {f(w["start"])});')
                js.append(f'tl.fromTo("#cw{gi}-{wi}", {{scale: 1}}, {{scale: 1.06, duration: 0.22, ease: "back.out(2.5)"}}, {f(w["start"])});')
            else:
                js.append(f'tl.to("#cw{gi}-{wi}", {{color: "#FFFFFF", duration: 0.08, ease: "none"}}, {f(w["start"])});')
        html.append(
            f'<div id="cg{gi}" class="clip cg" data-start="{f(start)}" data-duration="{f(end - start)}" data-track-index="2">'
            f'<div class="box" id="cgb{gi}">{" ".join(spans)}</div></div>'
        )
        js.append(f'tl.fromTo("#cgb{gi}", {{opacity: 0, y: 14}}, {{opacity: 1, y: 0, duration: 0.16, ease: "power2.out"}}, {f(start)});')
        js.append(f'tl.to("#cgb{gi}", {{opacity: 0, duration: 0.12, ease: "power2.in"}}, {f(end - 0.12)});')
        js.append(f'tl.set("#cgb{gi}", {{opacity: 0, visibility: "hidden"}}, {f(end)});')
    style = """
#root { position: absolute; inset: 0; pointer-events: none; }
#root .cg { position: absolute; left: 0; right: 0; bottom: 92px; text-align: center; overflow: visible; }
#root .box { display: inline-block; background: rgba(7,18,13,.88); border-radius: 18px; padding: 10px 24px 14px;
  font-family: Inter, sans-serif; font-weight: 700; font-size: 52px; line-height: 1.3; letter-spacing: -0.01em;
  color: rgba(255,255,255,.62); }
#root .cw { display: inline-block; transform-origin: 50% 70%; margin: 0 0.06em; }
#root .cw.key { font-weight: 900; padding: 0 10px; border-radius: 10px; background-image: linear-gradient(#B6F259, #B6F259);
  background-repeat: no-repeat; background-size: 0% 100%; background-position: 0 0; }
"""
    return f"""<template>
<style>{style}</style>
<div id="root" data-composition-id="captions" data-width="1920" data-height="1080">
{chr(10).join(html)}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{chr(10).join(js)}
window.__timelines["captions"] = tl;
</script>
</template>
"""


def write_srt():
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

    groups, cur = [], []
    for i, w in enumerate(WORDS):
        cur.append(w)
        nxt = WORDS[i + 1] if i + 1 < len(WORDS) else None
        if nxt is None or re.search(r"[.?!]$", w["text"]) or len(cur) >= 12 or nxt["para"] != w["para"]:
            groups.append(cur)
            cur = []
    lines = []
    for n, g in enumerate(groups, 1):
        lines += [str(n), f"{ts(g[0]['start'])} --> {ts(g[-1]['end'] + 0.2)}", " ".join(w["text"] for w in g), ""]
    (ROOT / "assets" / "turfbari-promo.en.srt").write_text("\n".join(lines), encoding="utf-8")


def build_scene(sid, start, end, shots):
    html = v2.build_scene(sid, start, end, shots)
    for a, b in HTML_TR.items():
        if b:
            html = html.replace(a, b)
    html = html.replace("</style>", EN_CSS + "</style>", 1)
    return html


def main():
    v1.copy_assets()
    comp = ROOT / "compositions"
    comp.mkdir(exist_ok=True)
    for old in comp.glob("*.html"):
        old.unlink()
    scenes = []
    for sid, start, end, shots in v2.SCENES:
        s0, s1 = warp(start), (TOTAL if sid == "cta" else warp(end))
        shots = translate(copy.deepcopy(shots))
        scenes.append((sid, s0, s1, shots))
        html = build_scene(sid, s0, s1, shots)
        (comp / f"{sid}.html").write_text(html, encoding="utf-8")
    (comp / "captions.html").write_text(build_captions(), encoding="utf-8")
    v1.SCENES = scenes
    index = v1.build_index().replace('<html lang="bn">', '<html lang="en">').replace(
        'data-composition-id="main" data-start="0"', 'data-composition-id="main" data-motion-blur="on" data-start="0"'
    )
    (ROOT / "index.html").write_text(index, encoding="utf-8")
    write_srt()
    left = [p.name for p in comp.glob("*.html") if BN.search(re.sub(r"<style>.*?</style>", "", p.read_text(encoding="utf-8"), flags=re.S))]
    if left:
        raise SystemExit(f"Bengali text left in: {left}")
    print(f"built {len(scenes)} scenes, total {TOTAL}s;", ", ".join(f"{s}@{a:.1f}" for s, a, _, _ in scenes))


if __name__ == "__main__":
    main()
