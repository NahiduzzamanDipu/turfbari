"""TurfBari promo v2: a continuous, cursor-driven walkthrough of the real app.

Each story chapter is one browser window ("world"). A cursor clicks real menu items, links and buttons; each
click opens the next real screenshot inside the same window, the URL bar updates, long pages scroll, and the
camera glides between the controls the voice names. The cursor's screen position is computed from the camera
so it stays locked on its target while the camera moves.

Run:  python tools/build2.py      (writes index.html + compositions/*.html)
"""

import json
import math
import re
from html import escape
from pathlib import Path

import build as v1
from build import CHROME, H, LIME, TOTAL, W, Scene, copy_assets, f, rich

ROOT = Path(__file__).resolve().parents[1]
WIN_H = H + CHROME  # window = 44 px chrome + 1080 px viewport
v1.IMAGES.update(
    {
        "district_dhaka": "turf-discovery/02-explore-district-filter.png",
        "login": "owner-dashboard/00-login.png",
        "bookings": "booking-management/05-bookings-list.png",
    }
)
TALL = {"turf_full": 1713}


def ease_inout(p):  # power2.inOut
    return 2 * p * p if p < 0.5 else 1 - (-2 * p + 2) ** 2 / 2


def cam_xy(z, fx, fy):
    x = W / 2 - z * fx
    y = H / 2 - z * (fy + CHROME)
    if z >= 1:
        x = min(0, max(W - z * W, x))
        y = min(0, max(H - z * WIN_H, y))
    else:
        x, y = (W - z * W) / 2, (H - z * WIN_H) / 2
    return x, y, z


class WorldScene(Scene):
    """Adds the 'world' (walkthrough) and 'chapter' shot kinds to the v1 scene builder."""

    def world(self, s):
        sid = s["id"]
        self.open_shot(s)
        self.html.append(f'<div id="{sid}-cam" class="cam" data-motion-blur="off"><div class="win" style="height:{WIN_H}px">')
        self.html.append('<div class="chrome" data-layout-ignore><i></i><i></i><i></i><span class="urlbox">')
        urls = []
        for i, (_, _, url, _) in enumerate(s["pages"]):
            if url not in urls:
                urls.append(url)
        for i, url in enumerate(urls):
            self.html.append(f'<b id="{sid}-url{i}" class="urlt{" on" if i == 0 else ""}">{escape(url)}</b>')
        self.html.append('</span></div><div class="viewport">')
        for i, (_, img, _, _) in enumerate(s["pages"]):
            self.html.append(
                f'<img id="{sid}-pg{i}" class="page{" first" if i == 0 else ""}" src="assets/shots/{img}.png" alt="">'
            )
        if "scan" in s:
            a, b, x, y, w, h = s["scan"]
            self.html.append(f'<div id="{sid}-scan" class="scan" style="left:{x}px;top:{y}px;width:{w}px;opacity:0"></div>')
        self.html.append("</div></div></div>")  # viewport, win, cam
        self.html.append("</div>")  # .enter

        # pages: route-style swap, url swap
        for i, (t, img, url, trans) in enumerate(s["pages"]):
            if i == 0:
                continue
            lt = f(self.lt(t))
            if trans == "modal":
                self.tw(f'tl.fromTo("#{sid}-pg{i}", {{opacity: 0}}, {{opacity: 1, duration: 0.22, ease: "power2.out"}}, {lt});')
            else:
                self.tw(
                    f'tl.fromTo("#{sid}-pg{i}", {{opacity: 0, y: 14}}, {{opacity: 1, y: 0, duration: 0.32, ease: "power3.out"}}, {lt});'
                )
            ui = urls.index(url)
            self.tw(f'tl.set("#{sid}-url{ui}", {{opacity: 1}}, {lt});')
            for uj in range(len(urls)):
                if uj != ui:
                    self.tw(f'tl.set("#{sid}-url{uj}", {{opacity: 0}}, {lt});')
            # hide earlier pages once covered (keeps the stack light)
            for j in range(i):
                self.tw(f'tl.set("#{sid}-pg{j}", {{opacity: 0}}, {f(self.lt(t) + 0.33)});')

        # scroll of tall pages: (t, dur, page_index, offset_px)
        for t, dur, pi, off in s.get("scroll", []):
            self.tw(
                f'tl.to("#{sid}-pg{pi}", {{y: {-off}, duration: {f(dur)}, ease: "power2.inOut"}}, {f(self.lt(t))});'
            )

        # camera timeline (global t, z, fx, fy, dur)
        cams = s["cam"]
        x, y, z = cam_xy(*cams[0][1:4])
        self.tw(f'tl.set("#{sid}-cam", {{x: {x:.1f}, y: {y:.1f}, scale: {z}}}, {f(self.lt(s["t0"]))});')
        for t, z, fx, fy, dur in cams[1:]:
            x, y, z = cam_xy(z, fx, fy)
            self.tw(
                f'tl.to("#{sid}-cam", {{x: {x:.1f}, y: {y:.1f}, scale: {z}, duration: {f(dur)}, ease: "power2.inOut"}}, {f(self.lt(t))});'
            )

        def cam_at(t):
            state = cams[0][1:4]
            for ct, z, fx, fy, dur in cams[1:]:
                if t >= ct + dur - 1e-6:
                    state = (z, fx, fy)
            return cam_xy(*state)

        def scroll_at(t, page_i):
            off = 0
            for st, dur, pi, o in s.get("scroll", []):
                if pi == page_i and t >= st + dur - 1e-6:
                    off = o
            return off

        def screen(t, px, py, page_i=None):
            cx, cy, cz = cam_at(t)
            off = scroll_at(t, page_i) if page_i is not None else 0
            return cx + cz * px, cy + cz * (py + CHROME - off)

        # cursor: actions in global time
        cur = s.get("cursor", [])
        if cur:
            self.html.append(
                f'<svg id="{sid}-cur" class="cursor" viewBox="0 0 28 28"><path d="M5 3l15.5 10.6-6.6 1.3 3.9 8.3-3.3 1.5-3.9-8.4L5 21.6z"/></svg>'
            )
            anchor = None
            first = True
            for act in cur:
                kind, t = act[0], act[1]
                if kind in ("in", "move"):
                    px, py = act[2], act[3]
                    page_i = act[5] if len(act) > 5 else None
                    dur = act[4] if len(act) > 4 else 0.7
                    sx, sy = screen(t + dur, px, py, page_i)
                    if first:
                        self.tw(
                            f'tl.fromTo("#{sid}-cur", {{x: {W + 60}, y: {H * 0.72:.0f}, opacity: 1}}, {{x: {sx:.1f}, y: {sy:.1f}, duration: {f(dur)}, ease: "power3.out"}}, {f(self.lt(t))});'
                        )
                        first = False
                    else:
                        self.tw(
                            f'tl.to("#{sid}-cur", {{x: {sx:.1f}, y: {sy:.1f}, opacity: 1, duration: {f(dur)}, ease: "power3.inOut"}}, {f(self.lt(t))});'
                        )
                    anchor = (px, py, page_i)
                elif kind == "click":
                    self.tw(
                        f'tl.to("#{sid}-cur", {{scale: 0.8, duration: 0.08, ease: "power2.in", yoyo: true, repeat: 1}}, {f(self.lt(t))});'
                    )
                elif kind == "hide":
                    self.tw(f'tl.to("#{sid}-cur", {{opacity: 0, duration: 0.2}}, {f(self.lt(t))});')
                    anchor = None
            # keep the cursor locked on its anchor during camera moves
            anchors = []
            a = None
            for act in cur:
                if act[0] in ("in", "move"):
                    dur = act[4] if len(act) > 4 else 0.7
                    a = (act[1] + dur, act[2], act[3], act[5] if len(act) > 5 else None)
                    anchors.append(("set", a))
                elif act[0] == "hide":
                    anchors.append(("clear", act[1]))
            for ct, z, fx, fy, dur in cams[1:]:
                live = None
                for kind, val in anchors:
                    if kind == "set" and val[0] <= ct + 1e-6:
                        live = val
                    elif kind == "clear" and val <= ct:
                        live = None
                if live is None:
                    continue
                busy = any(
                    act[0] in ("move", "in") and act[1] < ct + dur and act[1] + (act[4] if len(act) > 4 else 0.7) > ct
                    for act in cur
                )
                if busy:
                    continue
                cx, cy, cz = cam_xy(z, fx, fy)
                off = scroll_at(ct + dur, live[3]) if live[3] is not None else 0
                sx, sy = cx + cz * live[1], cy + cz * (live[2] + CHROME - off)
                self.tw(
                    f'tl.to("#{sid}-cur", {{x: {sx:.1f}, y: {sy:.1f}, duration: {f(dur)}, ease: "power2.inOut"}}, {f(self.lt(ct))});'
                )
        if "scan" in s:
            a, b, *_ = s["scan"]
            h = s["scan"][5]
            self.tw(f'tl.set("#{sid}-scan", {{opacity: 1}}, {f(self.lt(a))});')
            self.tw(f'tl.fromTo("#{sid}-scan", {{y: 0}}, {{y: {h}, duration: {f(b - a)}, ease: "none", immediateRender: false}}, {f(self.lt(a))});')
            self.tw(f'tl.set("#{sid}-scan", {{opacity: 0}}, {f(self.lt(b))});')
        self.tag_seq(sid, s.get("tags", []), s["t1"])
        for i, (t, text, until) in enumerate(s.get("callouts", [])):
            cid = f"{sid}-co{i}"
            self.html.append(f'<div id="{cid}" class="callout">{rich(text)}</div>')
            self.tw(f'tl.fromTo("#{cid}", {{opacity: 0, y: 24, filter: "blur(8px)"}}, {{opacity: 1, y: 0, filter: "blur(0px)", duration: 0.45, ease: "expo.out"}}, {f(self.lt(t))});')
            if until:
                self.fade_out(f"#{cid}", until)
        self.close_tail(s)

    def tag_seq(self, sid, tags, t1):
        """v2 tags: dark panel with a lime bar; the bar draws first, then the panel wipes open."""
        for i, (t, text) in enumerate(tags):
            tid = f"{sid}-tag{i}"
            self.html.append(f'<div id="{tid}" class="tag2"><i class="bar"></i><span class="tx">{rich(text)}</span></div>')
            lt = self.lt(t)
            self.tw(f'tl.fromTo("#{tid} .bar", {{scaleY: 0}}, {{scaleY: 1, duration: 0.25, ease: "expo.out"}}, {f(lt)});')
            self.tw(
                f'tl.fromTo("#{tid} .tx", {{clipPath: "inset(0% 100% 0% 0%)", x: -16}}, {{clipPath: "inset(0% 0% 0% 0%)", x: 0, duration: 0.45, ease: "expo.out"}}, {f(lt + 0.08)});'
            )
            end = tags[i + 1][0] - 0.02 if i + 1 < len(tags) else t1 - 0.02
            self.tw(f'tl.to("#{tid}", {{opacity: 0, x: -20, duration: 0.14, ease: "power3.in"}}, {f(self.lt(end) - 0.14)});')

    def chapter(self, s):
        """A lime panel sweeps across, the chapter name lands, the panel sweeps out revealing the next world."""
        sid = s["id"]
        d = s["t1"] - s["t0"]
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


# ------------------------------------------------------------------------------------ the walkthrough
NAV = {  # owner/manager sidebar targets (screenshot px)
    "Dashboard": (95, 181), "Book a slot": (95, 220), "Bookings": (90, 257), "Customers": (92, 295),
    "Fields": (78, 372), "Opening hours": (105, 408), "Pricing": (82, 447), "Reports": (84, 523), "Team": (74, 560),
}
EXPLORE_NAV = (862, 31)

PUBLIC = dict(
    id="pw", kind="world", t0=31.17, t1=66.05, enter="settle",
    pages=[
        (31.17, "home", "turfbari.com", "route"),
        (34.45, "explore", "turfbari.com/explore", "route"),
        (40.7, "district_dhaka", "turfbari.com/explore?district=dhaka", "route"),
        (41.85, "district", "turfbari.com/explore?district=dhaka&area=mirpur", "route"),
        (42.9, "search", "turfbari.com/explore?q=uttara", "route"),
        (44.85, "explore", "turfbari.com/explore", "route"),
        (53.4, "turf_full", "turfbari.com/turfs/green-arena-gulshan", "route"),
        (63.55, "turf_qr", "turfbari.com/turfs/green-arena-gulshan", "modal"),
    ],
    cam=[
        (31.17, 0.8, 960, 540, 0),
        (31.6, 1.35, 700, 330, 0.9),
        (33.2, 1.0, 960, 540, 0.8),
        (34.75, 1.75, 800, 420, 0.9),
        (39.75, 1.5, 560, 360, 0.7),
        (42.2, 1.6, 760, 200, 0.6),
        (44.0, 1.0, 960, 540, 0.6),
        (44.95, 2.0, 785, 440, 0.9),
        (50.75, 0.82, 960, 540, 0.9),
        (53.6, 1.0, 960, 540, 0.6),
        (60.45, 1.9, 1360, 230, 0.8),
        (62.25, 1.35, 1150, 700, 0.7),
        (63.7, 1.9, 960, 541, 0.7),
    ],
    scroll=[(54.3, 4.3, 6, 633), (59.4, 0.9, 6, 0)],
    cursor=[
        ("in", 33.3, *EXPLORE_NAV, 0.8),
        ("click", 34.3),
        ("move", 39.9, 511, 316, 0.6),
        ("click", 40.58),
        ("move", 41.1, 511, 398, 0.55),
        ("click", 41.75),
        ("move", 42.25, 640, 173, 0.45),
        ("click", 42.8),
        ("move", 43.95, *EXPLORE_NAV, 0.6),
        ("click", 44.7),
        ("move", 45.9, 785, 360, 0.6),
        ("move", 51.9, 785, 457, 0.8),
        ("click", 53.25),
        ("hide", 53.45),
        ("move", 60.6, 1445, 159, 0.9, 6),
        ("click", 61.95),
        ("move", 62.3, 1342, 818, 0.75, 6),
        ("click", 63.4),
        ("hide", 63.9),
    ],
    tags=[
        (32.0, "*অ্যাকাউন্ট* লাগে না"), (34.9, "*কাছের* টার্ফ আগে"), (38.8, "পাশে লেখা — কত *দূরে*"),
        (40.75, "*জেলা* আর এলাকা"), (42.95, "টার্ফের *নাম* দিয়ে সার্চ"), (45.05, "*ছবি*"),
        (46.4, "ইনডোর না *আউটডোর*"), (47.85, "কয়টি মাঠ • শুরুর *ভাড়া*"), (51.1, "দশ জায়গায় ফোন — *শেষ*"),
        (54.3, "ছবির *গ্যালারি*"), (56.4, "সুবিধা • মাঠ • *খোলার সময়*"), (58.9, "প্রতিটি স্লটের *ভাড়া*"),
        (60.9, "ম্যাপে এক ট্যাপে *রাস্তা*"), (63.75, "নিজস্ব *QR* কোড"),
    ],
    scan=(64.9, 65.95, 838, 420, 250, 250),
)

PHONE = dict(
    id="qr", kind="phone", t0=66.05, t1=81.16, side="right", enter="zoomin",
    screens=[(66.05, "q1"), (69.1, "q2"), (70.45, "q3"), (71.75, "q4"), (74.85, "q5"), (77.7, "q6")],
    titles=[(66.2, "স্ক্যান করলেই *বুকিং পেজ*", 68.95), (69.15, "তারিখ • মাঠ • *খালি সময়*", 71.6),
            (71.8, "নাম আর *মোবাইল নম্বর*", 74.7), (74.9, "*কনফার্ম* হলেই খেলা পাকা", 77.55),
            (77.75, "রেফারেন্স দিয়ে *স্ট্যাটাস*", None)],
    exit="dip",
)

OWNER = dict(
    id="ow", kind="world", t0=81.16, t1=105.05, enter="settle",
    pages=[
        (81.16, "login", "turfbari.com/login", "route"),
        (82.25, "dash", "turfbari.com/workspace", "route"),
        (89.05, "slots", "turfbari.com/workspace/book", "route"),
        (94.85, "discount", "turfbari.com/workspace/book", "route"),
        (99.8, "fields", "turfbari.com/workspace/fields", "route"),
        (100.65, "hours", "turfbari.com/workspace/hours", "route"),
        (101.6, "pricing", "turfbari.com/workspace/pricing", "route"),
        (103.45, "customers", "turfbari.com/workspace/customers", "route"),
    ],
    cam=[
        (81.16, 1.0, 960, 560, 0),
        (82.55, 1.55, 700, 241, 0.8),
        (85.6, 1.55, 1460, 241, 1.2),
        (87.95, 1.0, 960, 540, 0.7),
        (89.35, 1.45, 1082, 470, 0.8),
        (93.75, 1.2, 1300, 470, 0.6),
        (95.1, 1.75, 820, 640, 0.8),
        (97.85, 1.75, 640, 900, 0.7),
        (99.05, 1.0, 960, 540, 0.6),
    ],
    cursor=[
        ("in", 81.3, 960, 682, 0.7),
        ("click", 82.1),
        ("hide", 82.45),
        ("move", 88.1, *NAV["Book a slot"], 0.7),
        ("click", 88.95),
        ("move", 93.9, 1670, 545, 0.65),
        ("click", 94.7),
        ("move", 95.9, 373, 679, 0.55),
        ("click", 96.55),
        ("move", 99.1, *NAV["Fields"], 0.5),
        ("click", 99.68),
        ("move", 100.1, *NAV["Opening hours"], 0.4),
        ("click", 100.53),
        ("move", 101.05, *NAV["Pricing"], 0.4),
        ("click", 101.48),
        ("move", 102.85, *NAV["Customers"], 0.45),
        ("click", 103.33),
    ],
    tags=[
        (82.7, "আজকের বুকিং • *আজকের আদায়*"), (85.75, "মাসের আয় • মোট *বকেয়া*"), (89.25, "*বুক আ স্লট* বোর্ড"),
        (91.7, "খালি • বুকড • *অপেক্ষায়*"), (95.0, "ফোনের বুকিং — *কয়েক সেকেন্ডে*"), (97.85, "*ডিসকাউন্ট* আর অগ্রিমসহ"),
        (99.85, "*মাঠ*"), (100.7, "*খোলার সময়*"), (101.65, "পিক আওয়ার • *উইকেন্ড* ভাড়া"), (103.5, "কাস্টমারের বুকিং *ইতিহাস*"),
    ],
)

MANAGER = dict(
    id="mw", kind="world", t0=108.55, t1=118.95, enter="whip",
    pages=[
        (108.55, "team", "turfbari.com/workspace/team", "route"),
        (111.05, "m_login", "turfbari.com/login", "route"),
        (112.85, "m_dash", "turfbari.com/workspace", "route"),
        (113.6, "m_pending", "turfbari.com/workspace/bookings?status=pending", "route"),
        (116.0, "m_pay", "turfbari.com/workspace/bookings?status=pending", "modal"),
        (118.0, "m_customers", "turfbari.com/workspace/customers", "route"),
    ],
    cam=[
        (108.55, 1.0, 960, 540, 0),
        (108.95, 1.55, 1350, 170, 0.8),
        (110.75, 1.25, 960, 560, 0.5),
        (113.0, 1.0, 960, 540, 0.45),
        (113.75, 1.35, 1000, 300, 0.7),
        (116.1, 1.8, 960, 600, 0.7),
        (117.45, 1.0, 960, 540, 0.45),
    ],
    cursor=[
        ("in", 108.7, 1815, 68, 1.0),
        ("click", 110.05),
        ("move", 111.6, 960, 682, 0.8),
        ("click", 112.7),
        ("move", 112.95, *NAV["Bookings"], 0.45),
        ("click", 113.48),
        ("move", 114.8, 1082, 222, 0.7),
        ("click", 115.85),
        ("move", 116.6, 1230, 721, 0.55),
        ("click", 117.25),
        ("move", 117.5, *NAV["Customers"], 0.4),
        ("click", 117.92),
    ],
    tags=[
        (108.75, "টিম পেজ থেকে *ম্যানেজার*"), (111.2, "নিজের আলাদা *লগইন*"), (113.7, "প্রতিদিনের *বুকিং*"),
        (114.65, "রিকোয়েস্ট *কনফার্ম*"), (116.5, "*পেমেন্ট* রেকর্ড"), (118.05, "*কাস্টমার* সামলান"),
    ],
)

MONEY = dict(
    id="rw", kind="world", t0=126.76, t1=146.04, enter="whip", exit="zoom",
    pages=[
        (126.76, "bookings", "turfbari.com/workspace/bookings", "route"),
        (127.45, "payments", "turfbari.com/workspace/bookings", "modal"),
        (136.6, "reports", "turfbari.com/workspace/reports", "route"),
    ],
    cam=[
        (126.76, 1.0, 960, 540, 0),
        (127.6, 1.9, 1000, 470, 0.8),
        (131.5, 1.8, 960, 700, 0.8),
        (135.75, 1.0, 960, 540, 0.6),
        (136.95, 1.55, 833, 236, 0.8),
        (139.7, 1.4, 1082, 480, 0.8),
        (141.45, 1.6, 560, 780, 0.8),
        (143.3, 1.75, 1560, 120, 0.8),
    ],
    cursor=[
        ("in", 126.85, 1082, 222, 0.45),
        ("click", 127.32),
        ("move", 132.3, 846, 721, 0.6),
        ("click", 133.0),
        ("move", 134.6, 1230, 721, 0.5),
        ("click", 135.3),
        ("move", 135.75, *NAV["Reports"], 0.6),
        ("click", 136.48),
        ("hide", 136.75),
        ("move", 144.1, 1780, 68, 0.7),
        ("click", 144.9),
    ],
    tags=[
        (127.7, "মোট *ভাড়া*"), (129.1, "পরিশোধ আর *বাকি*"), (131.7, "ক্যাশ • *বিকাশ* • নগদ"), (134.8, "বুকিংয়ের সঙ্গেই *রেকর্ড*"),
        (136.75, "আদায় • খরচ • *নিট আয়*"), (139.85, "দিনভিত্তিক আদায়ের *চার্ট*"), (141.5, "কোন মাঠে কত *বুকিং*"),
        (143.5, "এক ক্লিকে *এক্সেল*"),
    ],
)


def chapter(cid, t0, kicker, title, dur=1.55):
    return dict(id=cid, kind="chapter", t0=t0, t1=t0 + dur, kicker=kicker, title=title)


old = {sid: shots for sid, _, _, shots in v1.SCENES}
hook = old["hook"]
intro = old["intro"]
owner_tail = [s for s in old["owner"] if s["id"] == "o8"]
manager_old = {s["id"]: s for s in old["manager"]}
benefits = old["benefits"]
cta = old["cta"]

SCENES = [
    ("hook", 0.0, 15.76, hook),
    ("intro", 15.76, 31.17, intro),
    ("public", 31.17, 81.16, [PUBLIC, PHONE, chapter("ch1", 31.17, "PLAYERS", "খেলোয়াড়দের *জন্য*")]),
    ("owner", 81.16, 107.62, [OWNER, *owner_tail, chapter("ch2", 81.16, "OWNER DASHBOARD", "টার্ফ *মালিকের* জন্য")]),
    ("manager", 107.62, 126.76, [manager_old["m1"], MANAGER, manager_old["m7"], manager_old["m8"]]),
    ("money", 126.76, 146.04, [MONEY, chapter("ch3", 126.76, "PAYMENTS & REPORTS", "পেমেন্ট আর *রিপোর্ট*")]),
    ("benefits", 146.04, 159.68, benefits),
    ("cta", 159.68, TOTAL, cta),
]

STYLE2 = """
#root .viewport { position: relative; width: 1920px; height: 1080px; overflow: hidden; background: #F7FBF8; }
#root .page { position: absolute; left: 0; top: 0; width: 1920px; opacity: 0; }
#root .page.first { opacity: 1; }
#root .urlbox { position: relative; display: inline-block; margin-left: 22px; width: 760px; height: 30px; background: #fff;
  border-radius: 9px; }
#root .urlt { position: absolute; left: 18px; top: 3px; font: 500 19px Inter, sans-serif; color: #33473C; opacity: 0; white-space: nowrap; }
#root .urlt.on { opacity: 1; }
#root .chrome span.urlbox { padding: 0; }
#root .tag2 { position: absolute; left: 200px; top: 118px; display: flex; align-items: stretch; filter: drop-shadow(0 16px 34px rgba(0,0,0,.35)); }
#root .tag2 .bar { width: 10px; background: #B6F259; border-radius: 6px 0 0 6px; transform-origin: 50% 0; }
#root .tag2 .tx { background: rgba(7,18,13,.94); color: #fff; font-weight: 700; font-size: 52px; line-height: 1.3;
  padding: 8px 30px 12px 24px; border-radius: 0 14px 14px 0; white-space: nowrap; }
#root .tag2 .hl { color: #B6F259; }
#root .chpanel { position: absolute; inset: 0; background: #B6F259; display: flex; flex-direction: column; justify-content: center;
  padding-left: 200px; }
#root .kicker { font: 700 40px "Barlow Condensed", sans-serif; letter-spacing: 6px; color: #006040; margin-bottom: 6px; }
#root .chtitle { font-weight: 700; font-size: 128px; line-height: 1.2; color: #10280B; }
#root .chtitle .hl { color: #006040; }
#root .cursor { width: 54px; height: 54px; fill: #fff; stroke: #0B1D13; stroke-width: 1.6px; stroke-linejoin: round;
  filter: drop-shadow(0 5px 8px rgba(0,0,0,.35)); transform-origin: 18% 12%; }
"""


def build_scene(sid, start, end, shots) -> str:
    sc = WorldScene(sid, start, end)
    for s in shots:
        getattr(sc, s["kind"])(s)
        if s["kind"] == "sidebars":
            for t, i in s["locks"]:
                sc.tw(
                    f'tl.fromTo("#{s["id"]}-lock{i}", {{scale: 2, opacity: 0}}, {{scale: 1, opacity: 1, duration: 0.35, ease: "back.out(2)"}}, {f(sc.lt(t))});'
                )
    body = "\n".join(sc.html)
    js = "\n".join(sc.js)
    return f"""<template>
<style>{v1.STYLE}{STYLE2}</style>
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


# ------------------------------------------------------------------------------------ captions v2
def build_captions() -> str:
    html = v1.build_captions()
    # marker-sweep highlight for key words; bigger, bolder captions
    html = html.replace(
        '#root .box { display: inline-block; background: rgba(7,18,13,.86); border-radius: 16px; padding: 8px 22px 14px;\n  font-family: "Hind Siliguri", sans-serif; font-weight: 600; font-size: 50px;',
        '#root .box { display: inline-block; background: rgba(7,18,13,.88); border-radius: 18px; padding: 8px 22px 14px;\n  font-family: "Hind Siliguri", sans-serif; font-weight: 700; font-size: 54px;',
    )
    html = html.replace(
        "#root .cw.key { font-weight: 700; }",
        "#root .cw.key { font-weight: 700; padding: 0 10px; border-radius: 10px; background-image: linear-gradient(#B6F259, #B6F259);"
        " background-repeat: no-repeat; background-size: 0% 100%; background-position: 0 0; }",
    )

    def key_tween(m):
        wid, t = m.group(1), m.group(2)
        return (
            f'tl.to("#{wid}", {{color: "#10280B", backgroundSize: "100% 100%", duration: 0.22, ease: "power2.out"}}, {t});'
        )

    html = re.sub(r'tl\.to\("#(cw[0-9-]+)", \{color: "' + LIME + r'", duration: 0\.08, ease: "none"\}, ([0-9.]+)\);', key_tween, html)
    return html


def write_srt():
    """Soft-subtitle track (also used as hidden, machine-readable text in the MP4)."""
    words = json.loads((ROOT / "assets" / "words.json").read_text(encoding="utf-8"))
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None or re.search(r"[।?!]$", w["text"]) or len(cur) >= 9 or nxt["para"] != w["para"]:
            groups.append(cur)
            cur = []

    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

    lines = []
    for n, g in enumerate(groups, 1):
        lines += [str(n), f"{ts(g[0]['start'])} --> {ts(g[-1]['end'] + 0.2)}", " ".join(w["text"] for w in g), ""]
    (ROOT / "assets" / "turfbari-promo.bn.srt").write_text("\n".join(lines), encoding="utf-8")


def main():
    copy_assets()
    comp = ROOT / "compositions"
    for old_file in comp.glob("*.html"):
        old_file.unlink()
    for sid, start, end, shots in SCENES:
        (comp / f"{sid}.html").write_text(build_scene(sid, start, end, shots), encoding="utf-8")
    (comp / "captions.html").write_text(build_captions(), encoding="utf-8")
    v1.SCENES = SCENES
    index = v1.build_index().replace(
        'data-composition-id="main" data-start="0"', 'data-composition-id="main" data-motion-blur="on" data-start="0"'
    )
    (ROOT / "index.html").write_text(index, encoding="utf-8")
    write_srt()
    print("built", len(SCENES), "scenes (v2 walkthrough)")


if __name__ == "__main__":
    main()
