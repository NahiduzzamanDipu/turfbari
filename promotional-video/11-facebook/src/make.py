"""Generate TurfBari Facebook page graphics (profile, cover, 10 posters) as HTML, then render PNGs with headless Chrome.

Usage: python make.py   (from anywhere)
"""

import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
PV = OUT.parent
A = (PV / "video" / "assets").as_uri()
LOGO = (PV / "01-brand-assets" / "logo" / "turfbari-logo-horizontal-transparent.png").as_uri()
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DOMAIN = "turfbari.onrender.com"

CSS = f"""
@font-face{{font-family:Hind;src:url('{A}/fonts/HindSiliguri-Medium.ttf');font-weight:500}}
@font-face{{font-family:Hind;src:url('{A}/fonts/HindSiliguri-SemiBold.ttf');font-weight:600}}
@font-face{{font-family:Hind;src:url('{A}/fonts/HindSiliguri-Bold.ttf');font-weight:700}}
@font-face{{font-family:Barlow;src:url('{A}/fonts/BarlowCondensed-Bold.ttf');font-weight:700}}
@font-face{{font-family:Barlow;src:url('{A}/fonts/BarlowCondensed-ExtraBold.ttf');font-weight:800}}
:root{{--lime:#B6F259;--em:#006040;--ink:#0B1D13;--bg:#07120D;--paper:#F2F8EC}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:var(--w);height:var(--h);overflow:hidden}}
body{{font-family:Hind,sans-serif;background:var(--bg);color:#fff;position:relative}}
.abs{{position:absolute}}
.lines{{position:absolute;inset:0;opacity:.07;background:
  radial-gradient(circle at 50% 50%,transparent 179px,#fff 180px,#fff 183px,transparent 184px),
  linear-gradient(90deg,transparent calc(50% - 2px),#fff calc(50% - 2px),#fff calc(50% + 1px),transparent calc(50% + 1px));}}
.glow{{position:absolute;border-radius:50%;filter:blur(90px);opacity:.35}}
.light body,.light{{background:var(--paper);color:var(--ink)}}
.logo{{height:64px}}
.badge{{display:flex;align-items:center;gap:12px;background:var(--ink);color:#fff;border:3px solid var(--lime);
  border-radius:999px;padding:8px 22px 8px 10px;font-weight:700;font-size:25px;line-height:1.1}}
.badge .ic{{width:40px;height:40px;border-radius:50%;background:var(--lime);display:grid;place-items:center}}
.badge small{{display:block;font-family:Barlow;font-weight:700;font-size:16px;letter-spacing:.14em;color:var(--lime)}}
.kick{{font-family:Barlow;font-weight:800;letter-spacing:.16em;font-size:24px;color:var(--lime);text-transform:uppercase}}
.light .kick{{color:var(--em)}}
h1{{font-weight:700;font-size:84px;line-height:1.12;letter-spacing:-.005em}}
h1 .hl{{background:linear-gradient(transparent 58%,var(--lime) 64%,var(--lime) 90%,transparent 90%);padding:0 6px;color:inherit}}
.dark h1 .hl{{background:none;color:var(--lime)}}
.sub{{font-weight:500;font-size:33px;line-height:1.45;opacity:.86}}
.foot{{position:absolute;left:0;right:0;bottom:0;height:120px;background:var(--lime);color:var(--ink);display:flex;
  align-items:center;justify-content:space-between;padding:0 60px}}
.foot .l{{font-weight:700;font-size:30px;line-height:1.15}}
.foot .l small{{display:block;font-weight:600;font-size:21px;opacity:.75}}
.foot .r{{font-family:Barlow;font-weight:800;font-size:38px;letter-spacing:.01em;display:flex;align-items:center;gap:12px}}
.win{{border-radius:22px;overflow:hidden;background:#fff;box-shadow:0 40px 90px rgba(0,0,0,.45),0 0 0 2px rgba(255,255,255,.08)}}
.light .win{{box-shadow:0 34px 80px rgba(11,29,19,.25),0 0 0 2px rgba(11,29,19,.06)}}
.bar{{height:46px;background:#EEF2EC;display:flex;align-items:center;gap:9px;padding:0 18px}}
.bar i{{width:13px;height:13px;border-radius:50%;background:#C9D2C6}}
.bar .u{{margin-left:14px;flex:1;height:28px;border-radius:8px;background:#fff;font:600 17px Hind;color:#4b5a50;
  display:flex;align-items:center;padding-left:14px;gap:8px}}
.shot{{background-repeat:no-repeat}}
.phone{{border-radius:48px;background:#0B1D13;padding:14px;box-shadow:0 40px 90px rgba(0,0,0,.5),0 0 0 2px rgba(255,255,255,.12)}}
.phone .scr{{border-radius:36px;overflow:hidden;background-repeat:no-repeat;background-size:100% auto}}
.chip{{display:inline-flex;align-items:center;gap:10px;background:rgba(182,242,89,.14);border:2px solid rgba(182,242,89,.5);
  color:#fff;border-radius:999px;padding:6px 20px;font-weight:600;font-size:26px}}
.light .chip{{background:#fff;border-color:rgba(0,96,64,.25);color:var(--ink)}}
.chip b{{color:var(--lime)}} .light .chip b{{color:var(--em)}}
.tick{{width:34px;height:34px;border-radius:50%;background:var(--lime);display:inline-grid;place-items:center;flex:none}}
.list{{display:flex;flex-direction:column;gap:18px;font-weight:600;font-size:31px}}
.list div{{display:flex;align-items:center;gap:16px}}
.callout{{position:absolute;background:var(--ink);color:#fff;border-radius:18px;padding:14px 22px;font-weight:700;font-size:28px;
  box-shadow:0 18px 40px rgba(0,0,0,.35);border-left:8px solid var(--lime);line-height:1.2}}
.callout small{{display:block;font-weight:600;font-size:20px;color:var(--lime)}}
"""

TOOL = ('<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#0B1D13" stroke-width="2.6" '
        'stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z"/></svg>')
CHECK = ('<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0B1D13" stroke-width="3.4" '
         'stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>')
GLOBE = ('<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#0B1D13" stroke-width="2.2" '
         'stroke-linecap="round"><circle cx="12" cy="12" r="9.5"/><path d="M2.5 12h19M12 2.5c3 3.2 3 15.8 0 19M12 2.5c-3 3.2-3 15.8 0 19"/></svg>')
LOCK = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4b5a50" stroke-width="2.6"><rect x="5" y="11" '
        'width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>')


def badge():
    return (f'<div class="badge"><span class="ic">{TOOL}</span><span>ডেভেলপমেন্ট চলছে'
            '<small>UNDER DEVELOPMENT</small></span></div>')


def foot(left="এখনও তৈরি হচ্ছে — ডেমো ঘুরে দেখুন", small="মতামত জানান, আপনার কথাতেই আরও ভালো হবে"):
    return (f'<div class="foot"><div class="l">{left}<small>{small}</small></div>'
            f'<div class="r">{GLOBE}{DOMAIN}</div></div>')


def shot(name, x, y, w, h, dw, src_w=1920):
    """A crop (x,y,w,h in source px) of a screenshot, displayed dw px wide."""
    s = dw / w
    return (f'<div class="shot" style="width:{dw}px;height:{round(h * s)}px;background-image:url({A}/shots/{name}.png);'
            f'background-size:{round(src_w * s)}px auto;background-position:{-round(x * s)}px {-round(y * s)}px"></div>')


def win(path, inner):
    return f'<div class="win"><div class="bar"><i></i><i></i><i></i><div class="u">{LOCK}{DOMAIN}{path}</div></div>{inner}</div>'


def phone(name, w=330, h=714, pos="top"):
    return (f'<div class="phone"><div class="scr" style="width:{w}px;height:{h}px;'
            f'background-image:url({A}/shots/{name}.png);background-position:center {pos}"></div></div>')


def tick(t):
    return f'<div><span class="tick">{CHECK}</span>{t}</div>'


def page(w, h, body, theme="dark"):
    return (f'<!doctype html><html class="{theme}" style="--w:{w}px;--h:{h}px"><head><meta charset="utf-8">'
            f'<style>{CSS}</style></head><body>{body}</body></html>')


def logo(theme="dark", size=64):
    t = "#fff" if theme == "dark" else "#0B1D13"
    b = "#B6F259" if theme == "dark" else "#006040"
    return (f'<div style="display:flex;align-items:center;gap:{size*0.22:.0f}px"><img src="{A}/mark.png" '
            f'style="width:{size}px;height:{size}px;border-radius:{size*0.24:.0f}px">'
            f'<span style="font:800 {size*0.92:.0f}px Barlow;letter-spacing:.005em;color:{t}">Turf<span style="color:{b}">Bari</span></span></div>')


def top(theme="dark"):
    lg = logo(theme)
    return f'<div class="abs" style="left:60px;right:60px;top:52px;display:flex;justify-content:space-between;align-items:center">{lg}{badge()}</div>'


def glow(x, y, size=520, color="#00A060"):
    return f'<div class="glow" style="left:{x}px;top:{y}px;width:{size}px;height:{size}px;background:{color}"></div>'


def head(kick, h1, sub, y=170, theme="dark", w=960):
    return (f'<div class="abs" style="left:60px;top:{y}px;width:{w}px"><div class="kick">{kick}</div>'
            f'<h1 style="margin-top:12px">{h1}</h1><div class="sub" style="margin-top:18px">{sub}</div></div>')


# --------------------------------------------------------------------------------------------- posters 1080x1350
P = {}

P["01-coming-soon"] = ("dark", f"""
<div class="abs" style="inset:0;background:url({A}/illus/night.png) center 62%/auto 100% no-repeat;opacity:.9"></div>
<div class="abs" style="inset:0;background:linear-gradient(180deg,#07120D 0%,rgba(7,18,13,.82) 34%,rgba(7,18,13,.15) 62%,rgba(7,18,13,.85) 88%)"></div>
{top()}
{head("Coming soon · TurfBari", 'মাঠ খুঁজতে আর<br><span class="hl">ফোনাফুনি</span> নয়।',
      'কাছের ফুটবল টার্ফ খোঁজা, ফাঁকা স্লট দেখা আর বুকিং — সব এক জায়গায়। টার্ফবাড়ি আসছে।')}
<div class="abs" style="left:60px;bottom:160px;display:flex;gap:14px;flex-wrap:wrap;width:960px">
  <span class="chip"><b>০১</b> টার্ফ খুঁজুন</span><span class="chip"><b>০২</b> স্লট দেখুন</span><span class="chip"><b>০৩</b> বুক করুন</span>
</div>
{foot()}""")

P["02-find-nearby"] = ("light", f"""
{glow(620, 380, 620, "#B6F259")}
{top("light")}
{head("Turfs near you", 'কাছের টার্ফ,<br><span class="hl">এক নজরে</span>',
      'লোকেশন চালু করলেই কাছের টার্ফগুলো আগে দেখাবে — কত কিলোমিটার দূরে, ভাড়া কত, সব কার্ডেই।', theme="light")}
<div class="abs" style="left:60px;top:640px;transform:rotate(-1.5deg)">{win("/", shot("home", 395, 690, 1135, 385, 960))}</div>
<div class="callout" style="right:70px;top:600px">৭০০ মিটার দূরে<small>দূরত্বসহ টার্ফ কার্ড</small></div>
<div class="abs" style="left:60px;top:1100px;display:flex;gap:14px"><span class="chip"><b>জেলা</b> ও এলাকা দিয়ে সার্চ</span><span class="chip"><b>রুফটপ</b> · ইনডোর · আউটডোর</span></div>
{foot()}""")

P["03-no-account"] = ("dark", f"""
<div class="lines"></div>{glow(560, 520, 600)}
{top()}
{head("No account needed", 'অ্যাকাউন্ট<br>ছাড়াই <span class="hl">বুকিং</span>',
      'নাম আর মোবাইল নম্বর দিন, স্লট বেছে নিন — বুকিং রিকোয়েস্ট চলে যাবে টার্ফে।', w=620)}
<div class="abs" style="left:60px;top:720px"><div class="list">
  {tick("সাইন আপ লাগবে না")}{tick("ফাঁকা স্লটে ট্যাপ")}{tick("রেফারেন্স দিয়ে স্ট্যাটাস চেক")}</div></div>
<div class="abs" style="right:330px;top:560px;transform:rotate(-5deg)">{phone("q3", 250, 540)}</div>
<div class="abs" style="right:60px;top:600px;transform:rotate(4deg)">{phone("q5", 250, 540)}</div>
{foot()}""")

P["04-live-slots"] = ("light", f"""
{glow(-160, 560, 640, "#B6F259")}
{top("light")}
{head("Live slot board", 'কোন স্লট ফাঁকা?<br><span class="hl">এখনই</span> দেখুন',
      'রঙ দেখেই বুঝবেন — কোনটা ফাঁকা, কোনটা বুকড, কোনটা কনফার্মের অপেক্ষায়। দিন বদলালেই নতুন বোর্ড।', theme="light")}
<div class="abs" style="left:60px;top:640px;transform:rotate(1.2deg)">{win("/workspace/slots", shot("slots", 300, 130, 1580, 540, 960))}</div>
<div class="callout" style="left:80px;top:1060px">টাইম, দল আর ভাড়া<small>এক বোর্ডেই পুরো দিন</small></div>
{foot()}""")

P["05-owner-dashboard"] = ("dark", f"""
<div class="lines"></div>{glow(420, 600, 700)}
{top()}
{head("For turf owners", 'আপনার টার্ফ,<br>আপনার <span class="hl">ড্যাশবোর্ড</span>',
      'আজকের বুকিং, আজকের কালেকশন, বাকি টাকা আর আসছে কোন দল — খুললেই চোখের সামনে।')}
<div class="abs" style="left:60px;top:650px;transform:rotate(-1.2deg)">{win("/workspace", shot("dash", 260, 0, 1650, 770, 960))}</div>
{foot()}""")

P["06-payments"] = ("light", f"""
{glow(640, 520, 560, "#B6F259")}
{top("light")}
{head("Payments, recorded", 'ক্যাশ, বিকাশ, নগদ —<br><span class="hl">সব হিসাব</span> এক জায়গায়',
      'প্রতিটা বুকিংয়ে কত পেলেন, কীভাবে পেলেন আর কত বাকি — খাতা ছাড়াই পরিষ্কার হিসাব।', theme="light")}
<div class="abs" style="left:150px;top:680px;transform:rotate(-1deg)">{win("/workspace/bookings", shot("payments", 560, 290, 820, 470, 780))}</div>
<div class="abs" style="left:60px;top:545px;display:flex;gap:12px"><span class="chip"><b>৳</b> ক্যাশ</span><span class="chip"><b>৳</b> বিকাশ</span><span class="chip"><b>৳</b> নগদ</span><span class="chip"><b>৳</b> বাকি হিসাব</span></div>
{foot()}""")

P["07-discount-advance"] = ("dark", f"""
<div class="lines"></div>{glow(-120, 640, 600)}
{top()}
{head("Discount & advance", 'ডিসকাউন্ট আর <span class="hl">অগ্রিম</span>,<br>নিজে থেকেই হিসাব',
      'রেগুলার দলকে ১০% ছাড়? অগ্রিম নিলেন ১,০০০ টাকা? বাকিটা কত — টার্ফবাড়ি নিজেই হিসাব করে দেয়।')}
<div class="abs" style="left:60px;top:600px;transform:rotate(-1.5deg)">{win("/workspace/slots", shot("discount", 300, 520, 540, 550, 560))}</div>
<div class="abs" style="right:60px;top:700px;width:380px;background:#fff;color:var(--ink);border-radius:24px;padding:30px 32px;
  box-shadow:0 40px 90px rgba(0,0,0,.45);transform:rotate(2deg);font-size:28px;font-weight:600;line-height:1.9">
  <div style="display:flex;justify-content:space-between"><span>ভাড়া</span><b>৳৫,৬০০</b></div>
  <div style="display:flex;justify-content:space-between;color:#0a7a4a"><span>ছাড় (১০%)</span><b>− ৳৫৬০</b></div>
  <div style="display:flex;justify-content:space-between;color:#0a7a4a"><span>অগ্রিম</span><b>− ৳১,০০০</b></div>
  <div style="border-top:3px dashed #cfd8cc;margin:10px 0 6px"></div>
  <div style="display:flex;justify-content:space-between;font-size:34px;font-weight:700"><span>বাকি</span>
    <b style="background:var(--lime);padding:0 12px;border-radius:10px">৳৪,০৪০</b></div>
</div>
{foot()}""")

P["08-manager"] = ("light", f"""
{glow(560, 600, 640, "#B6F259")}
{top("light")}
{head("Add your manager", 'ম্যানেজার চালাবে,<br>আপনি <span class="hl">নিশ্চিন্ত</span>',
      'ম্যানেজারের আলাদা লগইন — বুকিং কনফার্ম, পেমেন্ট আর কাস্টমার সামলাবে। দাম, সেটিংস থাকবে আপনার হাতে।', theme="light")}
<div class="abs" style="left:60px;top:680px;transform:rotate(-1deg)">{win("/workspace", shot("m_dash", 260, 0, 1650, 600, 960))}</div>
{foot()}""")

P["09-reports"] = ("dark", f"""
<div class="lines"></div>{glow(500, 560, 700)}
{top()}
{head("Reports & Excel", 'মাস শেষে হিসাব?<br><span class="hl">এক ক্লিকে</span> এক্সেল',
      'কালেকশন, খরচ, নিট লাভ, কোন মাঠে কত বুকিং — রিপোর্ট দেখুন, দরকার হলে এক্সেলে নামিয়ে নিন।')}
<div class="abs" style="left:60px;top:650px;transform:rotate(1.2deg)">{win("/workspace/reports", shot("reports", 260, 0, 1650, 760, 960))}</div>
{foot()}""")

P["10-list-your-turf"] = ("light", f"""
{glow(-140, 480, 620, "#B6F259")}
{top("light")}
{head("Turf owners · join early", 'আপনার টার্ফও<br><span class="hl">টার্ফবাড়িতে</span> আনুন',
      'আমরা এখন টার্ফবাড়ি তৈরি ও টেস্ট করছি। শুরুর দিকের টার্ফ মালিকদের মতামত নিয়েই এটা সাজাচ্ছি — পেজে মেসেজ দিন।', theme="light")}
<div class="abs" style="left:60px;top:700px"><div class="list">
  {tick("আবেদন করুন")}{tick("আমরা যাচাই করব")}{tick("লগইন পেয়ে দাম আর সময় সেট করুন")}</div></div>
<div class="abs" style="right:60px;top:590px;transform:rotate(2deg)">{win("/register-turf", shot("register", 985, 120, 540, 880, 420))}</div>
{foot("শুরুর দিকের টার্ফ মালিকদের খুঁজছি", "ইনবক্স করুন বা ডেমো দেখুন")}""")

# --------------------------------------------------------------------------------------------- profile + cover
PROFILE = f"""
<div class="abs" style="inset:0;background:radial-gradient(circle at 50% 46%,#0E6B47 0%,#063A27 55%,#041F15 100%)"></div>
<div class="abs" style="left:540px;top:540px;width:860px;height:860px;margin:-430px;border-radius:50%;border:6px solid rgba(182,242,89,.35)"></div>
<div class="abs" style="left:540px;top:540px;width:330px;height:330px;margin:-165px;border-radius:50%;border:4px solid rgba(255,255,255,.08)"></div>
<div class="abs" style="left:0;right:0;top:540px;height:4px;margin-top:-2px;background:rgba(255,255,255,.07)"></div>
<img class="abs" src="{A}/mark.png" style="left:540px;top:540px;width:600px;height:600px;margin:-300px;border-radius:120px;box-shadow:0 30px 80px rgba(0,0,0,.45)">
"""

COVER = f"""
<div class="abs" style="inset:0;background:url({A}/illus/night.png) center 64%/1640px auto no-repeat"></div>
<div class="abs" style="inset:0;background:linear-gradient(90deg,rgba(7,18,13,.15) 0%,rgba(7,18,13,.88) 30%,rgba(7,18,13,.88) 70%,rgba(7,18,13,.15) 100%)"></div>
<div class="abs" style="left:270px;right:270px;top:150px;text-align:center;display:flex;flex-direction:column;align-items:center">
  <div style="margin-bottom:14px">{logo("dark", 96)}</div>
  <h1 style="font-size:78px;line-height:1.15">প্রতিটি টার্ফের <span style="color:var(--lime)">ঠিকানা</span></h1>
  <div class="sub" style="font-size:32px;margin-top:10px">কাছের ফুটবল টার্ফ খুঁজুন · ফাঁকা স্লট দেখুন · বুকিং রিকোয়েস্ট পাঠান</div>
  <div style="display:flex;gap:18px;margin-top:30px;align-items:center">
    {badge()}
    <div class="badge" style="background:var(--lime);color:var(--ink);border-color:var(--lime);padding:8px 24px;font-family:Barlow;font-size:34px;font-weight:800">
      {GLOBE}{DOMAIN}</div>
  </div>
</div>
"""


def render(name, w, h, html, theme="dark"):
    src = HERE / f"{name}.html"
    src.write_text(page(w, h, html, theme), encoding="utf-8")
    png = OUT / f"{name}.png"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                    "--allow-file-access-from-files", "--virtual-time-budget=3000", f"--window-size={w},{h}",
                    f"--screenshot={png}", src.as_uri()], check=True, capture_output=True)
    print("wrote", png.name)


if __name__ == "__main__":
    import sys
    only = sys.argv[1:]
    jobs = [("00-profile-picture", 1080, 1080, PROFILE, "dark"), ("00-cover-photo", 1640, 924, COVER, "dark")]
    jobs += [(f"poster-{k}", 1080, 1350, v[1], v[0]) for k, v in P.items()]
    for name, w, h, html, theme in jobs:
        if not only or any(o in name for o in only):
            render(name, w, h, html, theme)
