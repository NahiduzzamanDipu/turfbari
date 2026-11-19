"""Generate the TurfBari promo as static HyperFrames HTML (index.html + compositions/*.html).

Every timed element is written into the HTML with a stable id, so the HyperFrames desktop app can
edit it. Re-run after changing SHOTS:  python tools/build.py
Times in SHOTS are global seconds on the voiceover clock (see assets/words.json).
"""

import json
import re
import shutil
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent
SHOT_SRC = PKG / "02-real-app-screenshots"
ILL_SRC = PKG / "03-reference-images" / "_illustrations"
LOGO_SRC = PKG / "01-brand-assets" / "logo"
TOTAL = 170.0
LIME, EMERALD, INK = "#B6F259", "#006040", "#0B1D13"
CHROME = 44
W, H = 1920, 1080

# ------------------------------------------------------------------------------------ assets
IMAGES = {
    "home": "public-homepage/01-home-hero.png",
    "register": "public-homepage/05-register-your-turf.png",
    "explore": "turf-discovery/01-explore-nearest-first.png",
    "district": "turf-discovery/03-explore-district-area-filter.png",
    "search": "turf-discovery/04-explore-search-by-name.png",
    "m_home": "turf-discovery/05-mobile-home.png",
    "m_explore": "turf-discovery/06-mobile-explore.png",
    "turf_full": "turf-details/05-turf-full-page.png",
    "turf_cover": "turf-details/01-turf-cover-gallery.png",
    "turf_qr": "turf-details/07-turf-qr-code.png",
    "q1": "qr-booking/01-mobile-turf-page-after-scan.png",
    "q2": "qr-booking/02-mobile-pick-field-and-date.png",
    "q3": "qr-booking/03-mobile-pick-time-slots.png",
    "q4": "qr-booking/04-mobile-booking-form.png",
    "q5": "qr-booking/05-mobile-request-sent.png",
    "q6": "qr-booking/06-mobile-booking-status.png",
    "dash": "owner-dashboard/01-dashboard.png",
    "team": "owner-dashboard/03-team-managers.png",
    "slots": "booking-management/01-book-a-slot-board.png",
    "discount": "booking-management/02-book-team-with-discount.png",
    "fields": "field-and-pricing/01-fields.png",
    "hours": "field-and-pricing/02-opening-hours.png",
    "pricing": "field-and-pricing/03-pricing-rules.png",
    "customers": "customer-management/01-customers.png",
    "m_login": "manager-dashboard/00-manager-login.png",
    "m_dash": "manager-dashboard/01-manager-dashboard.png",
    "m_pending": "manager-dashboard/08-manager-pending-requests.png",
    "m_pay": "manager-dashboard/09-manager-booking-details-and-payments.png",
    "m_customers": "manager-dashboard/10-manager-customers.png",
    "payments": "payment-management/01-booking-details-and-payments.png",
    "reports": "reports/01-reports-overview.png",
}
ILLUS = ["night", "goal", "ball", "brand"]
SIZES = {"turf_full": (1920, 1713)}
for k in ("m_home", "m_explore", "q1", "q2", "q3", "q4", "q5", "q6"):
    SIZES[k] = (390, 844)


def copy_assets():
    shots = ROOT / "assets" / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    for key, rel in IMAGES.items():
        shutil.copyfile(SHOT_SRC / rel, shots / f"{key}.png")
    ill = ROOT / "assets" / "illus"
    ill.mkdir(parents=True, exist_ok=True)
    for n in ILLUS:
        shutil.copyfile(ILL_SRC / f"{n}.png", ill / f"{n}.png")
    shutil.copyfile(LOGO_SRC / "turfbari-mark-1024.png", ROOT / "assets" / "mark.png")


# ------------------------------------------------------------------------------------ shots
# kinds: illus | ui | phone | split | paper | logo | title | sidebars | endcard
# cam: list of (t, zoom, fx, fy) in screenshot pixels; tags: list of (t, text) where *word* = highlight.
SCENES = [
    ("hook", 0.0, 15.76, [
        dict(id="h1", kind="illus", t0=0.0, t1=10.5, img="night", push=(1.0, 1.10), enter="none",
             titles=[(0.2, "দল রেডি, বুট রেডি", 2.8), (2.95, "মাঠ *কোথায়?*", 10.3)],
             chips=[(4.45, "আজ রাতে সময় খালি?"), (6.35, "ভাড়া কত?"), (7.3, "কাকে ফোন করবেন?")],
             darken=(8.5, 10.2, 0.55)),
        dict(id="h2", kind="paper", t0=10.5, t1=15.76, header=(10.8, "আর টার্ফ মালিকের দিন কাটে…"),
             cards=[(12.1, "খাতা", -4), (13.25, "ফোনকল", 3), (14.45, "বাকির হিসাব", -2)], exit="whip"),
    ]),
    ("intro", 15.76, 31.17, [
        dict(id="i1", kind="logo", t0=15.76, t1=19.0, mark_at=16.05, word_at=17.55),
        dict(id="i2", kind="split", t0=19.0, t1=26.9, phone="m_explore", win="dash",
             labels=[(19.15, "*খেলোয়াড়দের* জন্য"), (22.45, "*মালিক ও ম্যানেজারদের* জন্য")]),
        dict(id="i3", kind="logo", t0=26.9, t1=31.17, mark_at=26.95, word_at=27.1,
             lines=[(27.05, "সব এক প্ল্যাটফর্মে", 28.5), (28.65, "প্রতিটি টার্ফের *ঠিকানা*", None)], exit="zoom"),
    ]),
    ("discover", 31.17, 53.5, [
        dict(id="d1", kind="ui", t0=31.17, t1=34.5, img="home", enter="settle",
             cam=[(31.17, 0.82, 960, 540), (31.7, 1.45, 700, 360)], tags=[(32.3, "*অ্যাকাউন্ট* লাগে না")]),
        dict(id="d2", kind="ui", t0=34.5, t1=40.55, img="explore", enter="blur",
             cam=[(34.5, 0.82, 960, 540), (35.6, 1.75, 800, 420)],
             tags=[(34.7, "*কাছের* টার্ফ আগে"), (38.8, "পাশে লেখা — কত *দূরে*")]),
        dict(id="d3", kind="ui", t0=40.55, t1=42.75, img="district", enter="whip",
             cam=[(40.55, 1.15, 760, 420), (41.0, 1.8, 560, 380)], tags=[(40.7, "*জেলা* আর এলাকা")]),
        dict(id="d4", kind="ui", t0=42.75, t1=44.9, img="search", enter="whip",
             cam=[(42.75, 1.2, 820, 300), (43.1, 1.75, 820, 200)], tags=[(42.95, "টার্ফের *নাম* দিয়ে সার্চ")]),
        dict(id="d5", kind="ui", t0=44.9, t1=51.15, img="explore", enter="blur",
             cam=[(44.9, 1.3, 960, 500), (45.4, 2.2, 785, 470)],
             tags=[(45.0, "*ছবি*"), (46.4, "ইনডোর না *আউটডোর*"), (47.85, "কয়টি মাঠ • শুরুর *ভাড়া*")]),
        dict(id="d6", kind="phone", t0=51.15, t1=53.5, screens=[(51.15, "m_explore")], side="right",
             titles=[(51.3, "দশ জায়গায় ফোন করার দিন *শেষ*", None)]),
    ]),
    ("details", 53.5, 81.16, [
        dict(id="t1", kind="ui", t0=53.5, t1=60.6, img="turf_full", enter="whip", scroll=(54.1, 60.2),
             tags=[(54.3, "ছবির *গ্যালারি*"), (56.4, "সুবিধা • মাঠ • *খোলার সময়*"), (58.9, "প্রতিটি স্লটের *ভাড়া*")]),
        dict(id="t2", kind="ui", t0=60.6, t1=63.6, img="turf_cover", enter="blur",
             cam=[(60.6, 1.0, 960, 540), (61.0, 2.0, 1360, 230)], tags=[(61.0, "ম্যাপে এক ট্যাপে *রাস্তা*")],
             click=(62.3, 1445, 159)),
        dict(id="t3", kind="ui", t0=63.6, t1=66.05, img="turf_qr", enter="settle",
             cam=[(63.6, 1.2, 960, 541), (64.0, 1.9, 960, 541)], tags=[(63.8, "নিজস্ব *QR* কোড")],
             scan=(64.9, 65.95, 838, 420, 250, 250)),
        dict(id="t4", kind="phone", t0=66.05, t1=81.16, side="right", enter="zoomin",
             screens=[(66.05, "q1"), (69.1, "q2"), (70.45, "q3"), (71.75, "q4"), (74.85, "q5"), (77.7, "q6")],
             titles=[(66.2, "স্ক্যান করলেই *বুকিং পেজ*", 68.95), (69.15, "তারিখ • মাঠ • *খালি সময়*", 71.6),
                     (71.8, "নাম আর *মোবাইল নম্বর*", 74.7), (74.9, "*কনফার্ম* হলেই খেলা পাকা", 77.55),
                     (77.75, "রেফারেন্স দিয়ে *স্ট্যাটাস*", None)], exit="dip"),
    ]),
    ("owner", 81.16, 107.62, [
        dict(id="o1", kind="ui", t0=81.16, t1=89.05, img="dash", enter="settle",
             cam=[(81.16, 0.86, 960, 540), (82.6, 1.55, 700, 241), (85.6, 1.55, 1460, 241)],
             tags=[(81.35, "মালিকের *ড্যাশবোর্ড*"), (82.8, "আজকের বুকিং • *আজকের আদায়*"), (85.75, "মাসের আয় • মোট *বকেয়া*")]),
        dict(id="o2", kind="ui", t0=89.05, t1=94.75, img="slots", enter="whip",
             cam=[(89.05, 1.0, 960, 540), (89.5, 1.45, 1082, 470)],
             tags=[(89.2, "*বুক আ স্লট* বোর্ড"), (91.7, "খালি • বুকড • *অপেক্ষায়*")]),
        dict(id="o3", kind="ui", t0=94.75, t1=99.75, img="discount", enter="blur",
             cam=[(94.75, 1.0, 960, 540), (95.2, 1.75, 820, 640), (97.9, 1.75, 640, 900)],
             tags=[(95.0, "ফোনের বুকিং — *কয়েক সেকেন্ডে*"), (97.85, "*ডিসকাউন্ট* আর অগ্রিমসহ")]),
        dict(id="o4", kind="ui", t0=99.75, t1=100.6, img="fields", enter="whip",
             cam=[(99.75, 1.3, 1060, 380)], tags=[(99.8, "*মাঠ*")]),
        dict(id="o5", kind="ui", t0=100.6, t1=101.55, img="hours", enter="whip",
             cam=[(100.6, 1.3, 1060, 400)], tags=[(100.65, "*খোলার সময়*")]),
        dict(id="o6", kind="ui", t0=101.55, t1=103.4, img="pricing", enter="whip",
             cam=[(101.55, 1.45, 1000, 330)], tags=[(101.6, "পিক আওয়ার • *উইকেন্ড* ভাড়া")]),
        dict(id="o7", kind="ui", t0=103.4, t1=105.05, img="customers", enter="whip",
             cam=[(103.4, 1.3, 1060, 380)], tags=[(103.45, "কাস্টমারের বুকিং *ইতিহাস*")]),
        dict(id="o8", kind="paper", t0=105.05, t1=107.62, header=(105.15, "সবকিছু *গোছানো*"),
             cards=[(105.2, "খাতা", -3)], strike=(106.6, 0), exit="blur"),
    ]),
    ("manager", 107.62, 126.76, [
        dict(id="m1", kind="title", t0=107.62, t1=108.55, text="আর *ম্যানেজার?*"),
        dict(id="m2", kind="ui", t0=108.55, t1=111.05, img="team", enter="settle",
             cam=[(108.55, 1.0, 960, 540), (108.95, 1.55, 1300, 160)], tags=[(108.75, "টিম পেজ থেকে *ম্যানেজার*")],
             click=(110.1, 1815, 68)),
        dict(id="m3", kind="ui", t0=111.05, t1=113.05, img="m_login", enter="whip",
             cam=[(111.05, 1.05, 960, 540), (111.4, 1.45, 960, 520)], tags=[(111.2, "নিজের আলাদা *লগইন*")]),
        dict(id="m4", kind="ui", t0=113.05, t1=116.45, img="m_pending", enter="blur",
             cam=[(113.05, 1.0, 960, 540), (113.45, 1.4, 1100, 360)],
             tags=[(113.2, "প্রতিদিনের *বুকিং*"), (114.6, "রিকোয়েস্ট *কনফার্ম*")]),
        dict(id="m5", kind="ui", t0=116.45, t1=117.95, img="m_pay", enter="whip",
             cam=[(116.45, 1.4, 960, 560), (116.8, 1.85, 960, 620)], tags=[(116.55, "*পেমেন্ট* রেকর্ড")]),
        dict(id="m6", kind="ui", t0=117.95, t1=118.95, img="m_customers", enter="whip",
             cam=[(117.95, 1.3, 1060, 380)], tags=[(118.0, "*কাস্টমার* সামলান")]),
        dict(id="m7", kind="sidebars", t0=118.95, t1=124.0,
             locks=[(119.85, 0), (120.5, 1), (121.15, 2), (121.4, 3)],
             titles=[(119.05, "ভাড়া বদলানো • খরচ • রিপোর্ট • টিম", 121.9), (122.05, "শুধু *মালিকের* হাতে", None)]),
        dict(id="m8", kind="title", t0=124.0, t1=126.76, text="কাজ ভাগ হয়,\n*নিয়ন্ত্রণ* থাকে আপনার", exit="whip"),
    ]),
    ("money", 126.76, 146.04, [
        dict(id="p1", kind="ui", t0=126.76, t1=131.5, img="payments", enter="whip",
             cam=[(126.76, 1.0, 960, 540), (127.2, 1.9, 1000, 470)],
             tags=[(127.0, "মোট *ভাড়া*"), (129.1, "পরিশোধ আর *বাকি*")]),
        dict(id="p2", kind="ui", t0=131.5, t1=136.55, img="payments", enter="none",
             cam=[(131.5, 1.9, 1000, 470), (131.6, 1.8, 960, 700)],
             tags=[(131.7, "ক্যাশ • *বিকাশ* • নগদ"), (134.8, "বুকিংয়ের সঙ্গেই *রেকর্ড*")]),
        dict(id="p3", kind="ui", t0=136.55, t1=139.7, img="reports", enter="settle",
             cam=[(136.55, 1.0, 960, 540), (136.95, 1.55, 833, 236)], tags=[(136.75, "আদায় • খরচ • *নিট আয়*")]),
        dict(id="p4", kind="ui", t0=139.7, t1=143.25, img="reports", enter="none",
             cam=[(139.7, 1.55, 833, 236), (139.8, 1.4, 1082, 480), (141.45, 1.6, 560, 780)],
             tags=[(139.85, "দিনভিত্তিক আদায়ের *চার্ট*"), (141.5, "কোন মাঠে কত *বুকিং*")]),
        dict(id="p5", kind="ui", t0=143.25, t1=146.04, img="reports", enter="none",
             cam=[(143.25, 1.6, 560, 780), (143.35, 1.75, 1560, 120)], tags=[(143.5, "এক ক্লিকে *এক্সেল*")],
             click=(144.9, 1780, 68), exit="zoom"),
    ]),
    ("benefits", 146.04, 159.68, [
        dict(id="b1", kind="phone", t0=146.04, t1=150.1, side="right", enter="rise", screens=[(146.04, "m_home")],
             titles=[(146.2, "খেলোয়াড়দের জন্য\nসহজে টার্ফ *খোঁজা*", None)]),
        dict(id="b2", kind="ui", t0=150.1, t1=153.35, img="dash", enter="whip",
             cam=[(150.1, 0.86, 960, 540), (150.5, 1.15, 960, 470)], tags=[(150.25, "মালিকের জন্য *পরিষ্কার হিসাব*")]),
        dict(id="b3", kind="ui", t0=153.35, t1=155.65, img="m_dash", enter="whip",
             cam=[(153.35, 0.86, 960, 540), (153.7, 1.15, 960, 470)], tags=[(153.5, "ম্যানেজারের *স্পষ্ট দায়িত্ব*")]),
        dict(id="b4", kind="illus", t0=155.65, t1=159.68, img="ball", push=(1.0, 1.08), title_cls="big hero high",
             titles=[(155.72, "মাঠের বাইরের ঝামেলা কমলে,", 157.25), (157.3, "মাঠের ভেতরের\n*আনন্দটাই* বাড়ে", None)],
             flood=(159.28, 159.68)),
    ]),
    ("cta", 159.68, TOTAL, [
        dict(id="c1", kind="ui", t0=159.68, t1=163.55, img="register", enter="flood",
             cam=[(159.68, 1.0, 960, 540), (160.1, 1.2, 960, 470)], tags=[(159.85, "আজই আপনার টার্ফ *যুক্ত করুন*")]),
        dict(id="c2", kind="ui", t0=163.55, t1=165.1, img="explore", enter="whip",
             cam=[(163.55, 1.0, 960, 540), (163.9, 1.2, 960, 470)], tags=[(163.65, "পরের ম্যাচের *মাঠ*")]),
        dict(id="c3", kind="endcard", t0=165.1, t1=TOTAL),
    ]),
]

KEYWORDS = [
    "কোথায়", "টার্ফবাড়ি", "অ্যাকাউন্ট", "কাছের", "জেলা", "সার্চ", "গ্যালারি", "ম্যাপে", "QR", "স্ক্যান",
    "রিকোয়েস্ট", "কনফার্ম", "ড্যাশবোর্ড", "স্লট", "ডিসকাউন্ট", "অগ্রিম", "ম্যানেজার", "লগইন", "নিয়ন্ত্রণ",
    "বাকি", "বিকাশ", "রিপোর্টে", "নিট", "চার্ট", "এক্সেলে", "আনন্দটাই", "ঠিকানা", "যুক্ত", "সহজে", "খাতা",
    "ফোনকল", "খালি", "ভাড়া", "বকেয়া", "পেমেন্ট", "মালিকের", "খেলোয়াড়দের", "দূরে", "স্ট্যাটাস", "শেষ",
]


# ------------------------------------------------------------------------------------ helpers
def rich(text: str) -> str:
    """'a *b c* d' -> spans per word; words inside *...* get class hl. Newlines become <br>."""
    out, hl = [], False
    for line_i, line in enumerate(text.split("\n")):
        if line_i:
            out.append("<br>")
        for tok in re.findall(r"\*|[^\s*]+", line):
            if tok == "*":
                hl = not hl
                continue
            out.append(f'<span class="w{" hl" if hl else ""}">{escape(tok)}</span> ')
    return "".join(out).strip()


def cam_state(z, fx, fy, img_h=H):
    win_h = img_h + CHROME
    x = W / 2 - z * fx
    y = H / 2 - z * (fy + CHROME)
    if z * W >= W:
        x = min(0, max(W - z * W, x))
    else:
        x = (W - z * W) / 2
    if z * win_h >= H:
        y = min(0, max(H - z * win_h, y))
    else:
        y = (H - z * win_h) / 2
    return round(x, 1), round(y, 1), z


def f(v):
    return f"{v:.3f}".rstrip("0").rstrip(".")


class Scene:
    def __init__(self, sid, start, end):
        self.sid, self.start, self.end = sid, start, end
        self.html, self.js, self.z = [], [], 1

    def lt(self, t):  # local time
        return max(0.0, t - self.start)

    def tw(self, line):
        self.js.append(line)

    # ---- text animations
    def words_in(self, sel, t):
        self.tw(
            f'tl.fromTo("{sel} .w", {{opacity: 0, filter: "blur(6px)"}}, '
            f'{{opacity: 1, filter: "blur(0px)", duration: 0.14, ease: "power2.out", stagger: 0.07}}, {f(self.lt(t))});'
        )

    def fade_out(self, sel, t, dur=0.18):
        self.tw(
            f'tl.to("{sel}", {{opacity: 0, filter: "blur(8px)", duration: {dur}, ease: "power3.in"}}, {f(self.lt(t) - dur)});'
        )

    def tag_seq(self, sid, tags, t1):
        for i, (t, text) in enumerate(tags):
            tid = f"{sid}-tag{i}"
            self.html.append(f'<div id="{tid}" class="tag">{rich(text)}</div>')
            self.tw(
                f'tl.fromTo("#{tid}", {{clipPath: "inset(0% 100% 0% 0%)", opacity: 1}}, '
                f'{{clipPath: "inset(0% 0% 0% 0%)", duration: 0.35, ease: "expo.out"}}, {f(self.lt(t))});'
            )
            end = tags[i + 1][0] - 0.02 if i + 1 < len(tags) else t1 - 0.02
            self.tw(f'tl.to("#{tid}", {{opacity: 0, duration: 0.12, ease: "power3.in"}}, {f(self.lt(end) - 0.12)});')

    def title_seq(self, sid, titles, t1, cls="big"):
        for i, (t, text, until) in enumerate(titles):
            tid = f"{sid}-ti{i}"
            self.html.append(f'<div id="{tid}" class="{cls}">{rich(text)}</div>')
            self.words_in(f"#{tid}", t)
            if until is not None:
                self.fade_out(f"#{tid}", until)

    # ---- shot entries / exits on the .enter wrapper
    def enter(self, sid, kind, t):
        s, lt = f"#{sid}-in", self.lt(t)
        if kind == "settle":
            self.tw(f'tl.fromTo("{s}", {{scale: 1.06, opacity: 0, filter: "blur(10px)"}}, {{scale: 1, opacity: 1, filter: "blur(0px)", duration: 0.5, ease: "expo.out"}}, {f(lt)});')
        elif kind == "whip":
            self.tw(f'tl.fromTo("{s}", {{x: 260, opacity: 0, filter: "blur(20px)"}}, {{x: 0, opacity: 1, filter: "blur(0px)", duration: 0.3, ease: "expo.out"}}, {f(lt)});')
        elif kind == "blur":
            self.tw(f'tl.fromTo("{s}", {{opacity: 0, filter: "blur(8px)"}}, {{opacity: 1, filter: "blur(0px)", duration: 0.2, ease: "power2.out"}}, {f(lt)});')
        elif kind == "rise":
            self.tw(f'tl.fromTo("{s}", {{y: 90, opacity: 0}}, {{y: 0, opacity: 1, duration: 0.6, ease: "expo.out"}}, {f(lt)});')
        elif kind == "zoomin":
            self.tw(f'tl.fromTo("{s}", {{scale: 0.6, opacity: 0, filter: "blur(10px)"}}, {{scale: 1, opacity: 1, filter: "blur(0px)", duration: 0.55, ease: "expo.out"}}, {f(lt)});')
        elif kind == "flood":
            self.tw(f'tl.fromTo("{s}", {{opacity: 0}}, {{opacity: 1, duration: 0.35, ease: "power2.inOut"}}, {f(lt)});')

    def exit(self, sid, kind, t1):
        s = f"#{sid}-in"
        if kind == "whip":
            self.tw(f'tl.to("{s}", {{x: -300, opacity: 0, filter: "blur(20px)", duration: 0.28, ease: "power3.in"}}, {f(self.lt(t1) - 0.28)});')
        elif kind == "zoom":
            self.tw(f'tl.to("{s}", {{scale: 1.6, opacity: 0, filter: "blur(12px)", duration: 0.3, ease: "power3.in"}}, {f(self.lt(t1) - 0.3)});')
        elif kind == "blur":
            self.tw(f'tl.to("{s}", {{opacity: 0, filter: "blur(8px)", duration: 0.18, ease: "power3.in"}}, {f(self.lt(t1) - 0.18)});')
        elif kind == "dip":
            self.tw(f'tl.to("#{sid}-dip", {{opacity: 0.45, duration: 0.2, ease: "power2.in"}}, {f(self.lt(t1) - 0.2)});')

    def open_shot(self, s):
        self.z += 1
        d = s["t1"] - s["t0"]
        self.html.append(
            f'<div id="{s["id"]}" class="clip shot" data-start="{f(self.lt(s["t0"]))}" data-duration="{f(d)}" '
            f'data-track-index="1" style="z-index:{self.z}"><div id="{s["id"]}-in" class="enter">'
        )

    def close_shot(self, s, dip=False):
        self.html.append("</div>")
        if dip:
            self.html.append(f'<div id="{s["id"]}-dip" class="dip"></div>')
        self.html.append("</div>")

    # ---- shot kinds
    def ui(self, s):
        img = s["img"]
        iw, ih = SIZES.get(img, (1920, 1080))
        sid = s["id"]
        self.open_shot(s)
        self.html.append(f'<div id="{sid}-cam" class="cam" data-motion-blur="off"><div class="win" style="height:{ih + CHROME}px">')
        self.html.append('<div class="chrome" data-layout-ignore><i></i><i></i><i></i><span>turfbari.onrender.com</span></div>')
        self.html.append(f'<img class="shotimg" src="assets/shots/{img}.png" alt="">')
        if "scan" in s:
            _, _, x, y, w, h = s["scan"]
            self.html.append(f'<div id="{sid}-scan" class="scan" style="left:{x}px;top:{y + CHROME}px;width:{w}px;opacity:0"></div>')
        self.html.append("</div></div>")
        self.html.append("</div>")  # close .enter so tags/cursor sit above the camera
        cam = s.get("cam") or [(s["t0"], 1.0, 960, 540)]
        if "scroll" in s:
            a, b = s["scroll"]
            x0, y0, _ = cam_state(1.0, 960, 540 - CHROME, ih)
            self.tw(f'tl.set("#{sid}-cam", {{x: 0, y: 0, scale: 1}}, {f(self.lt(s["t0"]))});')
            self.tw(f'tl.to("#{sid}-cam", {{y: {H - (ih + CHROME)}, duration: {f(b - a)}, ease: "power1.inOut"}}, {f(self.lt(a))});')
        else:
            x, y, z = cam_state(cam[0][1], cam[0][2], cam[0][3], ih)
            self.tw(f'tl.set("#{sid}-cam", {{x: {x}, y: {y}, scale: {z}}}, {f(self.lt(s["t0"]))});')
            for t, z, fx, fy in cam[1:]:
                x, y, z = cam_state(z, fx, fy, ih)
                self.tw(f'tl.to("#{sid}-cam", {{x: {x}, y: {y}, scale: {z}, duration: 0.8, ease: "power2.inOut"}}, {f(self.lt(t))});')
        if "scan" in s:
            a, b, x, y, w, h = s["scan"]
            self.tw(f'tl.set("#{sid}-scan", {{opacity: 1}}, {f(self.lt(a))});')
            self.tw(f'tl.fromTo("#{sid}-scan", {{y: 0}}, {{y: {h}, duration: {f(b - a)}, ease: "none", immediateRender: false}}, {f(self.lt(a))});')
            self.tw(f'tl.set("#{sid}-scan", {{opacity: 0}}, {f(self.lt(b))});')
        self.tag_seq(sid, s.get("tags", []), s["t1"])
        if "click" in s:
            t, px, py = s["click"]
            last = cam[-1]
            x, y, z = cam_state(last[1], last[2], last[3], ih)
            sx, sy = x + z * px, y + z * (py + CHROME)
            self.html.append(f'<svg id="{sid}-cur" class="cursor" viewBox="0 0 24 24"><path d="M3 2l7.5 19 2.6-7.9L21 10.5z"/></svg>')
            self.tw(f'tl.fromTo("#{sid}-cur", {{x: {W + 80}, y: {H + 60}, opacity: 1}}, {{x: {f(sx - 6)}, y: {f(sy - 4)}, duration: 0.6, ease: "power3.out"}}, {f(self.lt(t) - 0.62)});')
            self.tw(f'tl.to("#{sid}-cur", {{scale: 0.82, duration: 0.07, ease: "power2.in", yoyo: true, repeat: 1, transformOrigin: "10% 10%"}}, {f(self.lt(t))});')
        self.close_tail(s)

    def close_tail(self, s):
        if s.get("exit") == "dip":
            self.html.append(f'<div id="{s["id"]}-dip" class="dip"></div>')
        self.html.append("</div>")
        self.enter(s["id"], s.get("enter", "blur"), s["t0"])
        if s.get("exit"):
            self.exit(s["id"], s["exit"], s["t1"])

    def phone(self, s):
        sid = s["id"]
        self.open_shot(s)
        side = s.get("side", "right")
        self.html.append(f'<div class="phone {side}"><div class="screen">')
        for i, (_, img) in enumerate(s["screens"]):
            self.html.append(f'<img id="{sid}-sc{i}" class="pscreen" src="assets/shots/{img}.png" alt="">')
        self.html.append("</div></div>")
        self.html.append("</div>")
        for i, (t, _) in enumerate(s["screens"]):
            if i == 0:
                self.tw(f'tl.set("#{sid}-sc0", {{opacity: 1}}, 0);')
            else:
                self.tw(f'tl.fromTo("#{sid}-sc{i}", {{opacity: 0, filter: "blur(8px)"}}, {{opacity: 1, filter: "blur(0px)", duration: 0.25, ease: "power2.out"}}, {f(self.lt(t))});')
        self.title_seq(sid, s.get("titles", []), s["t1"], cls=f"big side-{side}")
        self.close_tail(s)

    def illus(self, s):
        sid = s["id"]
        self.open_shot(s)
        self.html.append(f'<div id="{sid}-cam" class="illus"><img src="assets/illus/{s["img"]}.png" alt=""></div>')
        if "darken" in s:
            self.html.append(f'<div id="{sid}-dark" class="shade"></div>')
        self.html.append("</div>")
        a, b = s["push"]
        self.tw(f'tl.fromTo("#{sid}-cam", {{scale: {a}}}, {{scale: {b}, duration: {f(s["t1"] - s["t0"])}, ease: "power1.inOut"}}, {f(self.lt(s["t0"]))});')
        if "darken" in s:
            t, u, o = s["darken"]
            self.tw(f'tl.fromTo("#{sid}-dark", {{opacity: 0}}, {{opacity: {o}, duration: {f(u - t)}, ease: "power2.inOut"}}, {f(self.lt(t))});')
        self.title_seq(sid, s.get("titles", []), s["t1"], cls=s.get("title_cls", "big hero"))
        chips = s.get("chips", [])
        if chips:
            self.html.append(f'<div class="chips" id="{sid}-chips">')
            for i, (t, text) in enumerate(chips):
                self.html.append(f'<div id="{sid}-chip{i}" class="chip">{rich(text)}</div>')
            self.html.append("</div>")
            for i, (t, _) in enumerate(chips):
                self.tw(f'tl.fromTo("#{sid}-chip{i}", {{x: 60, opacity: 0, filter: "blur(10px)"}}, {{x: 0, opacity: 1, filter: "blur(0px)", duration: 0.5, ease: "expo.out"}}, {f(self.lt(t))});')
            self.fade_out(f"#{sid}-chips", 10.3, 0.2)
        if "flood" in s:
            a, b = s["flood"]
            self.html.append(f'<div id="{sid}-flood" class="flood"></div>')
            self.tw(f'tl.fromTo("#{sid}-flood", {{opacity: 0}}, {{opacity: 1, duration: {f(b - a)}, ease: "power2.inOut"}}, {f(self.lt(a))});')
        self.close_tail(s)

    def paper(self, s):
        sid = s["id"]
        self.open_shot(s)
        self.html.append('<div class="paperground"></div>')
        t, text = s["header"]
        self.html.append(f'<div id="{sid}-head" class="big top">{rich(text)}</div>')
        self.words_in(f"#{sid}-head", t)
        n = len(s["cards"])
        for i, (t, text, rot) in enumerate(s["cards"]):
            left = 960 - (n * 520 + (n - 1) * 40) / 2 + i * 560
            self.html.append(
                f'<div id="{sid}-card{i}" class="card" style="left:{left:.0f}px;top:430px;width:520px">'
                f'<span>{escape(text)}</span>'
                + (f'<i id="{sid}-strike" class="strike"></i>' if "strike" in s and i == s["strike"][1] else "")
                + "</div>"
            )
            self.tw(f'tl.fromTo("#{sid}-card{i}", {{scale: 1.35, rotation: {rot * 3}, opacity: 0, filter: "blur(10px)"}}, {{scale: 1, rotation: {rot}, opacity: 1, filter: "blur(0px)", duration: 0.45, ease: "expo.out"}}, {f(self.lt(t))});')
        self.html.append("</div>")
        if "strike" in s:
            t, _ = s["strike"]
            self.tw(f'tl.fromTo("#{sid}-strike", {{scaleX: 0}}, {{scaleX: 1, duration: 0.35, ease: "power3.out"}}, {f(self.lt(t))});')
        self.close_tail(s)

    def logo(self, s):
        sid = s["id"]
        self.open_shot(s)
        self.html.append(
            f'<div class="lockup" id="{sid}-lock"><img id="{sid}-mark" class="mark" src="assets/mark.png" alt="">'
            f'<div id="{sid}-word" class="wordmark">Turf<b>Bari</b></div></div>'
        )
        for i, (t, text, until) in enumerate(s.get("lines", [])):
            tid = f"{sid}-line{i}"
            self.html.append(f'<div id="{tid}" class="big under">{rich(text)}</div>')
            self.words_in(f"#{tid}", t)
            if until:
                self.fade_out(f"#{tid}", until)
        self.html.append("</div>")
        self.tw(f'tl.fromTo("#{sid}-mark", {{scale: 0.3, rotation: -12, opacity: 0}}, {{scale: 1, rotation: 0, opacity: 1, duration: 0.7, ease: "back.out(1.6)"}}, {f(self.lt(s["mark_at"]))});')
        self.tw(f'tl.fromTo("#{sid}-word", {{clipPath: "inset(0% 100% 0% 0%)", x: -30}}, {{clipPath: "inset(0% 0% 0% 0%)", x: 0, duration: 0.6, ease: "expo.out"}}, {f(self.lt(s["word_at"]))});')
        self.close_tail(s)

    def split(self, s):
        sid = s["id"]
        self.open_shot(s)
        self.html.append(f'<div id="{sid}-ph" class="phone left small"><div class="screen"><img class="pscreen" style="opacity:1" src="assets/shots/{s["phone"]}.png" alt=""></div></div>')
        self.html.append(f'<div id="{sid}-win" class="miniwin"><div class="chrome" data-layout-ignore><i></i><i></i><i></i><span>turfbari.onrender.com</span></div><img src="assets/shots/{s["win"]}.png" alt=""></div>')
        self.html.append("</div>")
        (t1, l1), (t2, l2) = s["labels"]
        self.html.append(f'<div id="{sid}-l1" class="label l1">{rich(l1)}</div><div id="{sid}-l2" class="label l2">{rich(l2)}</div>')
        self.tw(f'tl.fromTo("#{sid}-ph", {{y: 140, opacity: 0}}, {{y: 0, opacity: 1, duration: 0.6, ease: "expo.out"}}, {f(self.lt(t1))});')
        self.words_in(f"#{sid}-l1", t1 + 0.15)
        self.tw(f'tl.fromTo("#{sid}-win", {{x: 220, opacity: 0, filter: "blur(14px)"}}, {{x: 0, opacity: 1, filter: "blur(0px)", duration: 0.6, ease: "expo.out"}}, {f(self.lt(t2))});')
        self.words_in(f"#{sid}-l2", t2 + 0.15)
        self.tw(f'tl.to(["#{sid}-ph", "#{sid}-win"], {{scale: 0.94, duration: 0.8, ease: "power2.inOut"}}, {f(self.lt(26.0))});')
        self.close_tail(s)

    def title(self, s):
        sid = s["id"]
        self.open_shot(s)
        self.html.append("</div>")
        self.html.append(f'<div id="{sid}-t" class="big center">{rich(s["text"])}</div>')
        self.words_in(f"#{sid}-t", s["t0"] + 0.05)
        self.close_tail(s)

    def sidebars(self, s):
        """The two real navigation menus (labels exactly as in the app), rebuilt large enough to read."""
        sid = s["id"]
        self.open_shot(s)
        owner = ["Dashboard", "Book a slot", "Bookings", "Customers", "Maintenance", "Fields", "Opening hours",
                 "Pricing", "Expenses", "Reports", "Team", "Activity", "Subscription", "Settings"]
        manager = ["Dashboard", "Book a slot", "Bookings", "Customers", "Maintenance", "Fields", "Opening hours",
                   "Pricing", "Subscription", "Settings"]
        owner_only = {"Expenses": 0, "Reports": 1, "Team": 2, "Activity": 3}
        rows = []
        for name in owner:
            k = owner_only.get(name)
            lock = f'<svg id="{sid}-lock{k}" class="lock" viewBox="0 0 24 24"><rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3" fill="none"/></svg>' if k is not None else ""
            rows.append(f'<div id="{sid}-o-{name.replace(" ", "")}" class="navrow{" own" if k is not None else ""}">{name}{lock}</div>')
        mrows = []
        for name in manager:
            badge = f'<span id="{sid}-viewonly" class="viewonly">শুধু দেখা</span>' if name == "Pricing" else ""
            mrows.append(f'<div class="navrow">{name}{badge}</div>')
        self.html.append(
            f'<div class="sb owner" id="{sid}-own"><div class="sbhead">মালিক</div>{"".join(rows)}</div>'
            f'<div class="sb manager" id="{sid}-man"><div class="sbhead">ম্যানেজার</div>{"".join(mrows)}</div>'
        )
        self.html.append("</div>")
        self.title_seq(sid, s["titles"], s["t1"], cls="big top")
        self.tw(f'tl.fromTo(["#{sid}-own", "#{sid}-man"], {{y: 80, opacity: 0}}, {{y: 0, opacity: 1, duration: 0.55, ease: "expo.out", stagger: 0.12}}, {f(self.lt(s["t0"]))});')
        self.tw(f'tl.fromTo("#{sid}-viewonly", {{scale: 1.6, opacity: 0}}, {{scale: 1, opacity: 1, duration: 0.35, ease: "back.out(2)"}}, {f(self.lt(s["t0"] + 0.15))});')
        self.close_tail(s)

    def endcard(self, s):
        sid = s["id"]
        self.open_shot(s)
        self.html.append(
            f'<div class="lockup end" id="{sid}-lock"><img id="{sid}-mark" class="mark" src="assets/mark.png" alt="">'
            f'<div id="{sid}-word" class="wordmark">Turf<b>Bari</b></div></div>'
            f'<div id="{sid}-tag" class="big under2">{rich("প্রতিটি টার্ফের *ঠিকানা*")}</div>'
            f'<div id="{sid}-sub" class="sub">{rich("খেলা হোক আরও সহজে")}</div>'
            f'<div id="{sid}-ctas" class="ctas"><span class="btn solid">টার্ফ খুঁজুন</span><span class="btn ghost">আপনার টার্ফ যুক্ত করুন</span></div>'
            f'<div id="{sid}-url" class="url">turfbari.onrender.com</div>'
        )
        self.html.append("</div>")
        self.tw(f'tl.fromTo("#{sid}-mark", {{scale: 0.3, rotation: -12, opacity: 0}}, {{scale: 1, rotation: 0, opacity: 1, duration: 0.7, ease: "back.out(1.6)"}}, {f(self.lt(165.15))});')
        self.tw(f'tl.fromTo("#{sid}-word", {{clipPath: "inset(0% 100% 0% 0%)", x: -30}}, {{clipPath: "inset(0% 0% 0% 0%)", x: 0, duration: 0.6, ease: "expo.out"}}, {f(self.lt(165.5))});')
        self.words_in(f"#{sid}-tag", 165.75)
        self.words_in(f"#{sid}-sub", 166.55)
        self.tw(f'tl.fromTo("#{sid}-ctas .btn", {{y: 30, opacity: 0}}, {{y: 0, opacity: 1, duration: 0.5, ease: "expo.out", stagger: 0.1}}, {f(self.lt(167.3))});')
        self.tw(f'tl.fromTo("#{sid}-url", {{opacity: 0}}, {{opacity: 1, duration: 0.4, ease: "power2.out"}}, {f(self.lt(167.6))});')
        self.close_tail(s)


STYLE = """
@font-face { font-family: "Hind Siliguri"; src: url("assets/fonts/HindSiliguri-Medium.ttf"); font-weight: 500; }
@font-face { font-family: "Hind Siliguri"; src: url("assets/fonts/HindSiliguri-SemiBold.ttf"); font-weight: 600; }
@font-face { font-family: "Hind Siliguri"; src: url("assets/fonts/HindSiliguri-Bold.ttf"); font-weight: 700; }
@font-face { font-family: "Barlow Condensed"; src: url("assets/fonts/BarlowCondensed-Bold.ttf"); font-weight: 700; }
@font-face { font-family: "Barlow Condensed"; src: url("assets/fonts/BarlowCondensed-ExtraBold.ttf"); font-weight: 800; }
#root { position: absolute; inset: 0; overflow: hidden; background: #07120D; font-family: "Hind Siliguri", sans-serif; }
#root .ground { position: absolute; inset: 0; background: url("assets/illus/brand.png") center/cover; }
#root .shot { position: absolute; inset: 0; }
#root .enter { position: absolute; inset: 0; transform-origin: 50% 50%; }
#root .cam { position: absolute; left: 0; top: 0; width: 1920px; transform-origin: 0 0; }
#root .win { position: relative; width: 1920px; border-radius: 22px; overflow: hidden; background: #F7FBF8;
  box-shadow: 0 50px 120px rgba(0,0,0,.5); }
#root .chrome { height: 44px; background: #E3ECE6; display: flex; align-items: center; gap: 10px; padding-left: 22px; }
#root .chrome i { width: 13px; height: 13px; border-radius: 50%; background: #B9C7BE; }
#root .chrome span { margin-left: 22px; background: #fff; border-radius: 9px; padding: 3px 18px; font: 500 19px Inter, sans-serif; color: #33473C; }
#root .shotimg { display: block; width: 1920px; }
#root .scan { position: absolute; height: 6px; background: #B6F259; border-radius: 3px; }
#root .tag { position: absolute; left: 200px; top: 122px; background: #B6F259; color: #10280B; font-weight: 700; font-size: 54px;
  line-height: 1.3; padding: 8px 30px 12px; border-radius: 16px; box-shadow: 0 18px 40px rgba(0,0,0,.28); white-space: nowrap; }
#root .tag .hl { color: #006040; }
#root .w { display: inline-block; }
#root .big { position: absolute; color: #fff; font-weight: 700; font-size: 96px; line-height: 1.28; text-shadow: 0 6px 30px rgba(0,0,0,.45); }
#root .big .hl { color: #B6F259; }
#root .big.hero { left: 200px; top: 300px; width: 1300px; }
#root .big.hero.high { top: 118px; }
#root .big.top { left: 200px; top: 150px; width: 1520px; font-size: 72px; }
#root .big.center { left: 0; right: 0; top: 360px; text-align: center; font-size: 110px; }
#root .big.side-right { left: 200px; top: 330px; width: 900px; font-size: 84px; }
#root .big.side-left { right: 200px; top: 330px; width: 900px; font-size: 84px; }
#root .big.under { left: 0; right: 0; top: 640px; text-align: center; font-size: 72px; }
#root .chips { position: absolute; left: 1180px; top: 300px; display: flex; flex-direction: column; gap: 26px; align-items: flex-start; }
#root .chip { background: rgba(7,18,13,.82); color: #fff; font-weight: 600; font-size: 50px; padding: 10px 30px 14px; border-radius: 14px;
  border-left: 8px solid #B6F259; }
#root .illus { position: absolute; inset: 0; transform-origin: 50% 55%; }
#root .illus img { width: 1920px; height: 1080px; display: block; }
#root .shade { position: absolute; inset: 0; background: #020806; opacity: 0; }
#root .flood { position: absolute; inset: 0; background: #B6F259; opacity: 0; }
#root .dip { position: absolute; inset: 0; background: #000; opacity: 0; }
#root .paperground { position: absolute; inset: 0; background: #0A1611 url("assets/illus/brand.png") center/cover; opacity: 1; }
#root .card { position: absolute; height: 300px; background: #FAF6EA; border-radius: 10px; box-shadow: 0 30px 70px rgba(0,0,0,.45);
  display: flex; align-items: center; justify-content: center; color: #1B1B1B; font-weight: 700; font-size: 104px; }
#root .strike { position: absolute; left: 40px; right: 40px; top: 50%; height: 16px; margin-top: -2px; background: #DF2225; border-radius: 8px;
  transform-origin: 0 50%; }
#root .phone { position: absolute; top: 40px; width: 457px; height: 956px; border-radius: 64px; background: #0B0F0D; padding: 14px;
  box-shadow: 0 50px 120px rgba(0,0,0,.55); }
#root .phone.right { left: 1330px; }
#root .phone.left { left: 210px; }
#root .phone .screen { position: relative; width: 429px; height: 928px; border-radius: 50px; overflow: hidden; background: #F7FBF8; }
#root .pscreen { position: absolute; left: 0; top: 0; width: 429px; height: 928px; opacity: 0; }
#root .phone.small { top: 175px; width: 340px; height: 708px; padding: 12px; border-radius: 50px; }
#root .phone.small .screen { width: 316px; height: 684px; border-radius: 40px; }
#root .phone.small .pscreen { width: 316px; height: 684px; }
#root .miniwin { position: absolute; left: 700px; top: 200px; width: 1060px; border-radius: 16px; overflow: hidden; background: #F7FBF8;
  box-shadow: 0 50px 120px rgba(0,0,0,.5); }
#root .miniwin img { display: block; width: 1060px; }
#root .miniwin .chrome { height: 36px; }
#root .label { position: absolute; color: #fff; font-weight: 700; font-size: 52px; text-shadow: 0 4px 20px rgba(0,0,0,.4); }
#root .label .hl { color: #B6F259; }
#root .label.l1 { left: 200px; top: 70px; }
#root .label.l2 { left: 700px; top: 110px; }
#root .lockup { position: absolute; left: 0; right: 0; top: 330px; display: flex; align-items: center; justify-content: center; gap: 34px; }
#root .lockup .mark { width: 200px; height: 200px; border-radius: 44px; }
#root .wordmark { font-family: "Barlow Condensed", sans-serif; font-weight: 800; font-size: 210px; color: #fff; line-height: 1; letter-spacing: 1px; }
#root .wordmark b { color: #B6F259; font-weight: 800; }
#root .lockup.end { top: 210px; }
#root .big.under2 { left: 0; right: 0; top: 470px; text-align: center; font-size: 84px; }
#root .sub { position: absolute; left: 0; right: 0; top: 600px; text-align: center; color: rgba(255,255,255,.85); font-size: 52px; font-weight: 600; }
#root .ctas { position: absolute; left: 0; right: 0; top: 712px; display: flex; justify-content: center; gap: 28px; }
#root .btn { font-size: 46px; font-weight: 700; padding: 12px 40px 16px; border-radius: 16px; }
#root .btn.solid { background: #B6F259; color: #10280B; }
#root .btn.ghost { color: #fff; border: 3px solid rgba(255,255,255,.85); }
#root .url { position: absolute; left: 0; right: 0; top: 830px; text-align: center; color: #fff; font: 700 58px "Barlow Condensed", sans-serif; letter-spacing: 3px; }
#root .cursor { position: absolute; left: 0; top: 0; width: 62px; height: 62px; fill: #fff; stroke: #0B1D13; stroke-width: 1.5px; z-index: 50;
  filter: drop-shadow(0 6px 10px rgba(0,0,0,.35)); }
#root .sb { position: absolute; top: 262px; width: 560px; background: #F7FBF8; border-radius: 22px; overflow: hidden;
  box-shadow: 0 40px 100px rgba(0,0,0,.45); padding-bottom: 10px; }
#root .sb.owner { left: 330px; }
#root .sb.manager { left: 1030px; }
#root .sbhead { height: 74px; background: #006040; color: #fff; font-size: 42px; font-weight: 700; text-align: center; line-height: 74px; margin-bottom: 8px; }
#root .navrow { position: relative; height: 36px; line-height: 36px; padding: 0 28px; font: 500 28px Inter, sans-serif; color: #24362C; }
#root .navrow.own { color: #0B1D13; font-weight: 700; }
#root .lock { position: absolute; right: 26px; top: 5px; width: 26px; height: 26px; fill: #006040; stroke: #006040; stroke-width: 2.2; }
#root .viewonly { margin-left: 14px; font: 600 28px "Hind Siliguri", sans-serif; background: #FFF1C9; color: #7A4B00; padding: 0 10px 2px; border-radius: 8px; }
"""


def sidebar_fix(html: str) -> str:
    # lock icons next to Expenses (y≈485), Reports (y≈523), Team (y≈561) in the owner crop (scale 1.085, offset 84-150)
    ys = {3: 84 + int(485 * 1.085) - 150 - 26, 4: 84 + int(523 * 1.085) - 150 - 26, 5: 84 + int(561 * 1.085) - 150 - 26}
    for i, y in ys.items():
        html = html.replace(f'-lock{i}" class="lock" style="top:0px"', f'-lock{i}" class="lock" style="top:{y}px"')
    return html


def build_scene(sid, start, end, shots) -> str:
    sc = Scene(sid, start, end)
    for s in shots:
        getattr(sc, s["kind"])(s)
        if s["kind"] == "sidebars":
            for t, i in s["locks"]:
                sc.tw(f'tl.fromTo("#{s["id"]}-lock{i}", {{scale: 2, opacity: 0}}, {{scale: 1, opacity: 1, duration: 0.35, ease: "back.out(2)"}}, {f(sc.lt(t))});')
                sc.tw(f'tl.to("#{s["id"]}-own .navrow.own:nth-of-type({i + 10})", {{backgroundColor: "#E9FBD0", duration: 0.2}}, {f(sc.lt(t))});')
    body = "\n".join(sc.html)
    js = "\n".join(sc.js)
    return f"""<template>
<style>{STYLE}</style>
<div id="root" data-composition-id="{sid}" data-width="1920" data-height="1080" data-layout-allow-overlap>
<div class="ground"></div>
{body}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{js}
window.__timelines["{sid}"] = tl;
</script>
</template>
"""


# ------------------------------------------------------------------------------------ captions
def build_captions() -> str:
    words = json.loads((ROOT / "assets" / "words.json").read_text(encoding="utf-8"))
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        text = w["text"]
        brk = (
            nxt is None
            or re.search(r"[।?!—]$", text)
            or (re.search(r",$", text) and len(cur) >= 2)
            or len(cur) >= 5
            or (nxt and nxt["start"] - w["end"] >= 0.15 and len(cur) >= 2)
            or (nxt and nxt["para"] != w["para"])
        )
        if brk:
            groups.append(cur)
            cur = []
    html, js = [], []
    for gi, g in enumerate(groups):
        start = max(0.15, g[0]["start"] - 0.06)
        nxt_start = groups[gi + 1][0]["start"] - 0.06 if gi + 1 < len(groups) else TOTAL
        end = min(g[-1]["end"] + 0.25, nxt_start - 0.02)
        key_done = False
        spans = []
        for wi, w in enumerate(g):
            is_key = not key_done and any(k in w["text"] for k in KEYWORDS)
            key_done = key_done or is_key
            spans.append(f'<span id="cw{gi}-{wi}" class="cw{" key" if is_key else ""}">{escape(w["text"])}</span>')
            js.append(
                f'tl.to("#cw{gi}-{wi}", {{color: "{LIME if is_key else "#FFFFFF"}", duration: 0.08, ease: "none"}}, {f(w["start"])});'
            )
            if is_key:
                js.append(
                    f'tl.fromTo("#cw{gi}-{wi}", {{scale: 1}}, {{scale: 1.08, duration: 0.22, ease: "back.out(2.5)"}}, {f(w["start"])});'
                )
        html.append(
            f'<div id="cg{gi}" class="clip cg" data-start="{f(start)}" data-duration="{f(end - start)}" data-track-index="2">'
            f'<div class="box" id="cgb{gi}">{" ".join(spans)}</div></div>'
        )
        js.append(f'tl.fromTo("#cgb{gi}", {{opacity: 0, y: 14}}, {{opacity: 1, y: 0, duration: 0.16, ease: "power2.out"}}, {f(start)});')
        js.append(f'tl.to("#cgb{gi}", {{opacity: 0, duration: 0.12, ease: "power2.in"}}, {f(end - 0.12)});')
        js.append(f'tl.set("#cgb{gi}", {{opacity: 0, visibility: "hidden"}}, {f(end)});')
    style = """
@font-face { font-family: "Hind Siliguri"; src: url("assets/fonts/HindSiliguri-SemiBold.ttf"); font-weight: 600; }
@font-face { font-family: "Hind Siliguri"; src: url("assets/fonts/HindSiliguri-Bold.ttf"); font-weight: 700; }
#root { position: absolute; inset: 0; pointer-events: none; }
#root .cg { position: absolute; left: 0; right: 0; bottom: 96px; text-align: center; overflow: visible; }
#root .box { display: inline-block; background: rgba(7,18,13,.86); border-radius: 16px; padding: 8px 22px 14px;
  font-family: "Hind Siliguri", sans-serif; font-weight: 600; font-size: 50px; line-height: 1.35; color: rgba(255,255,255,.7); }
#root .cw { display: inline-block; transform-origin: 50% 70%; margin: 0 0.14em; }
#root .cw.key { font-weight: 700; }
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


def build_index() -> str:
    hosts = []
    for sid, start, end, _ in SCENES:
        hosts.append(
            f'<div id="{sid}" data-composition-id="{sid}" data-composition-src="compositions/{sid}.html" '
            f'data-start="{f(start)}" data-duration="{f(end - start)}" data-track-index="1" data-track-kind="graphics" '
            f'data-width="1920" data-height="1080" style="z-index:1"></div>'
        )
    hosts.append(
        f'<div id="captions" data-composition-id="captions" data-composition-src="compositions/captions.html" '
        f'data-start="0" data-duration="{f(TOTAL)}" data-track-index="2" data-track-kind="captions" '
        f'data-width="1920" data-height="1080" style="z-index:10"></div>'
    )
    hosts.append('<audio id="voiceover" src="assets/voiceover.mp3" data-start="0" data-track-index="3" data-volume="1"></audio>')
    return f"""<!doctype html>
<html lang="bn">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: #07120D; }}
      #root {{ position: relative; width: 100%; height: 100%; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{f(TOTAL)}" data-width="1920" data-height="1080">
      {chr(10).join("      " + h for h in hosts).strip()}
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""


def main():
    copy_assets()
    comp = ROOT / "compositions"
    comp.mkdir(exist_ok=True)
    for sid, start, end, shots in SCENES:
        (comp / f"{sid}.html").write_text(build_scene(sid, start, end, shots), encoding="utf-8")
    (comp / "captions.html").write_text(build_captions(), encoding="utf-8")
    (ROOT / "index.html").write_text(build_index(), encoding="utf-8")
    print("built", len(SCENES), "scenes")


if __name__ == "__main__":
    main()
