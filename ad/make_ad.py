"""Sudoku app promo video — 1080x1920 @30fps, ~24s, with synthesized music.

Usage:  python3 make_ad.py            -> out/sudoku_ad.mp4
        python3 make_ad.py --preview  -> a few still frames in out/
"""
import math, os, random, subprocess, sys, wave
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
W, H, FPS, DUR = 1080, 1920, 30, 24.0
SR = 44100
random.seed(7)
np.random.seed(7)

# ---------------------------------------------------------------- palette
NAVY = (12, 14, 38)
PURPLE = (58, 22, 92)
GOLD = (255, 196, 61)
CYAN = (64, 224, 255)
PINK = (255, 84, 140)
WHITE = (255, 255, 255)
GREEN = (80, 230, 150)

# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def prog(t, a, b): return clamp((t - a) / (b - a))
def ease_out(x): return 1 - (1 - x) ** 3
def ease_in_out(x): return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2
def ease_back(x, s=1.9): x -= 1; return 1 + (s + 1) * x ** 3 + s * x ** 2
def spring(x):
    if x <= 0: return 0.0
    return 1 - math.exp(-7 * x) * math.cos(12 * x)
def lerp(a, b, x): return a + (b - a) * x

# ---------------------------------------------------------------- fonts / text
F_HEAD = os.path.join(HERE, "assets", "Lalezar.ttf")
F_BODY = os.path.join(HERE, "assets", "Cairo.ttf")

@lru_cache(None)
def font(path, size, weight=800):
    f = ImageFont.truetype(path, size)
    if path == F_BODY:
        try:
            axes = f.get_variation_axes()
            vals = [weight if b"ght" in (a.get("name") or b"") or "ght" in str(a.get("name")) else a["default"] for a in axes]
            f.set_variation_by_axes(vals)
        except Exception:
            pass
    return f

@lru_cache(None)
def text_layer(text, path, size, color=WHITE, glow=None, stroke=0, stroke_color=(0, 0, 0)):
    f = font(path, size)
    kw = dict(direction="rtl", language="ar") if any("؀" <= ch <= "ۿ" for ch in text) else {}
    x0, y0, x1, y1 = f.getbbox(text, stroke_width=stroke, **kw)
    pad = 60
    im = Image.new("RGBA", (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((pad - x0, pad - y0), text, font=f, fill=color + (255,), stroke_width=stroke,
           stroke_fill=stroke_color + (255,), **kw)
    if glow:
        g = Image.new("RGBA", im.size, glow + (0,))
        g.putalpha(im.getchannel("A").filter(ImageFilter.GaussianBlur(18)))
        g2 = Image.alpha_composite(g, g)
        im = Image.alpha_composite(g2, im)
    return im

def paste_center(dst, layer, cx, cy, scale=1.0, alpha=1.0, rot=0.0):
    if alpha <= 0.003 or scale <= 0.01: return
    if abs(scale - 1) > 1e-3:
        layer = layer.resize((max(1, int(layer.width * scale)), max(1, int(layer.height * scale))), Image.BILINEAR)
    if rot: layer = layer.rotate(rot, Image.BILINEAR, expand=True)
    if alpha < 0.999:
        a = layer.getchannel("A").point(lambda v: int(v * alpha))
        layer = layer.copy(); layer.putalpha(a)
    dst.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))

def txt(dst, s, cx, cy, size, path=F_HEAD, color=WHITE, scale=1, alpha=1, glow=None, stroke=0, rot=0):
    paste_center(dst, text_layer(s, path, size, color, glow, stroke), cx, cy, scale, alpha, rot)

# ---------------------------------------------------------------- backgrounds
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
_r = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2)
VIGNETTE = np.clip(1.15 - _r * 1.25, 0.25, 1.0)[..., None]

@lru_cache(None)
def gradient(c1, c2, c3=None):
    k = (yy / H)[..., None]
    a, b = np.array(c1, np.float32), np.array(c2, np.float32)
    g = a * (1 - k) + b * k
    if c3 is not None:
        glow = np.exp(-(((xx - W / 2) / 520) ** 2 + ((yy - H * .55) / 700) ** 2))[..., None]
        g = g + np.array(c3, np.float32) * glow * .55
    return Image.fromarray(np.clip(g, 0, 255).astype(np.uint8)).convert("RGBA")

PARTICLES = [dict(x=random.uniform(0, W), y=random.uniform(0, H), s=random.uniform(3, 9),
                  v=random.uniform(20, 90), d=str(random.randint(1, 9)), ph=random.uniform(0, 6.28))
             for _ in range(46)]

def particles(img, t, color=(255, 255, 255), digits=True, alpha=90):
    d = ImageDraw.Draw(img)
    for i, p in enumerate(PARTICLES):
        y = (p["y"] - p["v"] * t) % H
        x = p["x"] + 30 * math.sin(t * .8 + p["ph"])
        a = int(alpha * (.5 + .5 * math.sin(t * 2 + p["ph"])))
        if digits and i % 3 == 0:
            f = font(F_BODY, int(p["s"] * 7), 700)
            d.text((x, y), p["d"], font=f, fill=color + (a // 2,))
        else:
            r = p["s"] / 2
            d.ellipse((x - r, y - r, x + r, y + r), fill=color + (a,))

def rrect(d, box, r, **kw): d.rounded_rectangle(box, r, **kw)

# ---------------------------------------------------------------- sudoku data
def make_board():
    rows = [g * 3 + r for g in random.sample(range(3), 3) for r in random.sample(range(3), 3)]
    cols = [g * 3 + c for g in random.sample(range(3), 3) for c in random.sample(range(3), 3)]
    nums = random.sample(range(1, 10), 9)
    return [[nums[(3 * (r % 3) + r // 3 + c) % 9] for c in cols] for r in rows]

BOARD = make_board()
GIVEN = [[random.random() < .42 for _ in range(9)] for _ in range(9)]
FOCUS = (4, 6)  # the cell the camera dives into
GIVEN[FOCUS[0]][FOCUS[1]] = False
EMPTY = [(r, c) for r in range(9) for c in range(9) if not GIVEN[r][c] and (r, c) != FOCUS]
random.shuffle(EMPTY)
GIVEN_ORDER = [(r, c) for r in range(9) for c in range(9) if GIVEN[r][c]]
random.shuffle(GIVEN_ORDER)

GX, GY, GS = 540, 1040, 900   # grid centre + size
CELL = GS / 9

def cell_center(r, c): return GX - GS / 2 + (c + .5) * CELL, GY - GS / 2 + (r + .5) * CELL

# ---------------------------------------------------------------- camera
def camera(img, zoom=1.0, cx=W / 2, cy=H / 2, rot=0.0, shake=0.0, t=0.0):
    if shake:
        cx += shake * math.sin(t * 91) * 18; cy += shake * math.cos(t * 77) * 18
        rot += shake * math.sin(t * 53) * 1.5
    if abs(zoom - 1) < 1e-4 and abs(cx - W / 2) < .5 and abs(cy - H / 2) < .5 and not rot:
        return img
    a = math.radians(rot); ca, sa = math.cos(a) / zoom, math.sin(a) / zoom
    # output (x,y) -> input: R^-1 * (p - centre)/zoom + (cx,cy)
    data = (ca, sa, cx - ca * W / 2 - sa * H / 2, -sa, ca, cy + sa * W / 2 - ca * H / 2)
    return img.transform((W, H), Image.AFFINE, data, resample=Image.BILINEAR)

# ================================================================= SCENES
def scene_hook(t):  # 0 – 3.5  : doom-scrolling phone
    img = gradient((6, 8, 20), (20, 16, 44), (30, 60, 140)).copy()
    particles(img, t, (120, 160, 255), digits=False, alpha=60)
    d = ImageDraw.Draw(img)
    pin = ease_back(prog(t, 0, .7))
    px, py, pw, ph = 540, 1180 + (1 - pin) * 900, 500, 960
    # phone glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((px - 420, py - 520, px + 420, py + 520), fill=(60, 140, 255, 90))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(90)))
    d = ImageDraw.Draw(img)
    rrect(d, (px - pw / 2 - 16, py - ph / 2 - 16, px + pw / 2 + 16, py + ph / 2 + 16), 70, fill=(28, 30, 40))
    screen = Image.new("RGBA", (pw, ph), (235, 238, 245, 255))
    sd = ImageDraw.Draw(screen)
    off = (t * 1500) % 330
    for i in range(-1, 5):
        y = i * 330 - off + 60
        rrect(sd, (24, y, pw - 24, y + 300), 26, fill=(255, 255, 255), outline=(215, 220, 230), width=3)
        sd.ellipse((44, y + 20, 104, y + 80), fill=[(255, 120, 150), (120, 170, 255), (255, 200, 90)][i % 3])
        sd.rounded_rectangle((120, y + 30, 380, y + 50), 10, fill=(200, 205, 215))
        sd.rounded_rectangle((44, y + 100, pw - 44, y + 280), 18, fill=[(190, 210, 255), (255, 210, 220), (210, 245, 220)][i % 3])
    mask = Image.new("L", (pw, ph), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw, ph), 56, fill=255)
    img.paste(screen, (int(px - pw / 2), int(py - ph / 2)), mask)
    # clock counter
    mins = int(lerp(12, 187, ease_in_out(prog(t, .6, 3.3))))
    tl = prog(t, .6, .9)
    rrect(d, (px - 150, py - ph / 2 - 120, px + 150, py - ph / 2 - 40), 40, fill=(255, 84, 140, int(255 * tl)))
    txt(img, f"{mins // 60}h {mins % 60:02d}m", px, py - ph / 2 - 82, 50, F_BODY, WHITE, alpha=tl)
    # headline
    a = prog(t, .35, .8)
    txt(img, "بتقلّب في الموبايل", 540, 250, 118, F_HEAD, WHITE, spring(a) if a else 0, a, glow=CYAN)
    b = prog(t, .8, 1.2)
    txt(img, "بالساعات؟", 540, 410, 150, F_HEAD, GOLD, spring(b) if b else 0, b, glow=(255, 120, 0))
    return camera(img, lerp(1.0, 1.18, ease_in_out(prog(t, 0, 3.5))), 540, 900)

def scene_problem(t):  # 3.5 – 6 : brain is idle -> wake it up
    img = gradient((30, 6, 20), (8, 6, 16), (120, 20, 50)).copy()
    particles(img, t, (255, 100, 120), digits=False, alpha=50)
    a = prog(t, 0, .35)
    txt(img, "وعقلك", 540, 720, 170, F_HEAD, WHITE, lerp(2.6, 1, ease_out(a)), a)
    b = prog(t, .35, .7)
    txt(img, "واقف مكانه!", 540, 930, 190, F_HEAD, PINK, lerp(2.6, 1, ease_out(b)), b, glow=(255, 0, 60))
    c = prog(t, 1.35, 1.7)
    if c:
        d = ImageDraw.Draw(img)
        rrect(d, (140, 1180, 940, 1370), 95, fill=GOLD + (int(255 * c),))
        txt(img, "يلا نصحّيه", 540, 1272, 120, F_HEAD, NAVY, spring(c), c)
    shake = 1.0 if .35 < t < .75 else (.5 if 1.35 < t < 1.6 else 0)
    zoom = lerp(1.0, 1.35, ease_in_out(prog(t, 1.8, 2.5)))  # push toward next scene
    return camera(img, zoom, 540, 1150, shake=shake, t=t)

def draw_grid(img, t, fill_t, focus_t):
    d = ImageDraw.Draw(img)
    x0, y0 = GX - GS / 2, GY - GS / 2
    # card behind the grid
    k = ease_out(prog(t, 0, .5))
    rrect(d, (x0 - 30, y0 - 30, x0 + GS + 30, y0 + GS + 30), 46, fill=(255, 255, 255, int(245 * k)))
    # focus cell highlight: row / col / box
    if focus_t > 0:
        fr, fc = FOCUS
        a = int(90 * focus_t)
        d.rectangle((x0, y0 + fr * CELL, x0 + GS, y0 + (fr + 1) * CELL), fill=(120, 170, 255, a))
        d.rectangle((x0 + fc * CELL, y0, x0 + (fc + 1) * CELL, y0 + GS), fill=(120, 170, 255, a))
        pulse = .5 + .5 * math.sin(t * 9)
        cx, cy = cell_center(fr, fc)
        d.rectangle((cx - CELL / 2, cy - CELL / 2, cx + CELL / 2, cy + CELL / 2),
                    fill=(255, 196, 61, int((140 + 90 * pulse) * focus_t)))
    # lines draw in
    for i in range(10):
        p = ease_out(prog(t, .2 + i * .04, .75 + i * .04))
        if not p: continue
        w = 9 if i % 3 == 0 else 3
        col = (30, 34, 70) if i % 3 == 0 else (160, 168, 200)
        L = GS * p
        d.line((x0 + i * CELL, y0, x0 + i * CELL, y0 + L), fill=col, width=w)
        d.line((x0, y0 + i * CELL, x0 + L, y0 + i * CELL), fill=col, width=w)
    # givens pop
    for n, (r, c) in enumerate(GIVEN_ORDER):
        p = prog(t, .6 + n * .03, 1.0 + n * .03)
        if p:
            cx, cy = cell_center(r, c)
            txt(img, str(BOARD[r][c]), cx, cy, 72, F_BODY, (30, 34, 70), spring(p), 1)
    # user-filled cells cascade
    for n, (r, c) in enumerate(EMPTY):
        p = prog(fill_t, n / len(EMPTY) * .8, n / len(EMPTY) * .8 + .2)
        if p:
            cx, cy = cell_center(r, c)
            txt(img, str(BOARD[r][c]), cx, cy, 72, F_BODY, (40, 110, 255), spring(p), 1)

def scene_grid(t):  # 6 – 12 : puzzle builds, dive into a cell, solve, zoom out
    img = gradient(NAVY, PURPLE, (40, 90, 200)).copy()
    particles(img, t + 6, (255, 220, 140))
    a = prog(t, .1, .5)
    txt(img, "حرّك عقلك", 540, 330, 140, F_HEAD, WHITE, spring(a) if a else 0, a, glow=CYAN)
    focus_t = prog(t, 2.0, 2.4) * (1 - prog(t, 3.8, 4.1))
    fill_t = prog(t, 3.7, 4.9)
    draw_grid(img, t, fill_t, focus_t)
    fr, fc = FOCUS
    cx, cy = cell_center(fr, fc)
    # candidate numbers flicker then the 7... well, the real answer lands
    if 2.4 < t < 3.25:
        cand = [1, 3, 5, 8, BOARD[fr][fc]][int((t - 2.4) * 8) % 5]
        txt(img, str(cand), cx, cy, 72, F_BODY, (150, 150, 170), 1, .7)
    land = prog(t, 3.25, 3.55)
    if land:
        txt(img, str(BOARD[fr][fc]), cx, cy, 76, F_BODY, (20, 160, 90), lerp(3, 1, ease_out(land)), land, glow=GREEN)
        # burst
        bp = prog(t, 3.25, 3.9)
        if 0 < bp < 1:
            d = ImageDraw.Draw(img)
            for k in range(14):
                ang = k / 14 * 6.283
                r0, r1 = 40 + bp * 90, 60 + bp * 170
                d.line((cx + math.cos(ang) * r0, cy + math.sin(ang) * r0, cx + math.cos(ang) * r1, cy + math.sin(ang) * r1),
                       fill=GOLD + (int(255 * (1 - bp)),), width=6)
    # solved!
    s = prog(t, 5.0, 5.35)
    if s:
        d = ImageDraw.Draw(img)
        x0, y0 = GX - GS / 2, GY - GS / 2
        d.rounded_rectangle((x0 - 30, y0 - 30, x0 + GS + 30, y0 + GS + 30), 46, outline=GREEN + (int(255 * (1 - prog(t, 5.4, 6))),), width=14)
        confetti(img, t - 5.0)
        txt(img, "أحسنت!", 540, 1680, 150, F_HEAD, GREEN, spring(s), s, glow=(0, 160, 80), stroke=4)
    # camera: settle -> dive into focus cell (zoom in) -> pull back (zoom out)
    zin = ease_in_out(prog(t, 1.6, 2.4))
    zout = ease_in_out(prog(t, 3.7, 4.6))
    z = lerp(1.0, 3.2, zin) if zout == 0 else lerp(3.2, .96, zout)
    tx = lerp(540, cx, zin) if zout == 0 else lerp(cx, 540, zout)
    ty = lerp(1000, cy, zin) if zout == 0 else lerp(cy, 1000, zout)
    z *= lerp(1.25, 1.0, ease_out(prog(t, 0, .45)))  # arrive-zoom from previous scene
    return camera(img, z, tx, ty, rot=lerp(-4, 0, zin) if zout == 0 else 0, shake=.4 if 3.25 < t < 3.45 else 0, t=t)

CONF = [dict(x=random.uniform(100, 980), vx=random.uniform(-260, 260), vy=random.uniform(-1500, -700),
             c=random.choice([GOLD, PINK, CYAN, GREEN, WHITE]), r=random.uniform(0, 360), w=random.uniform(14, 26))
        for _ in range(90)]

def confetti(img, t):
    if t <= 0: return
    d = ImageDraw.Draw(img)
    for p in CONF:
        x = p["x"] + p["vx"] * t
        y = 1900 + p["vy"] * t + 1400 * t * t
        ang = math.radians(p["r"] + t * 540)
        w, h = p["w"], p["w"] * .45 * abs(math.cos(t * 7 + p["r"]))
        pts = [(x + math.cos(ang) * dx - math.sin(ang) * dy, y + math.sin(ang) * dx + math.cos(ang) * dy)
               for dx, dy in ((-w, -h), (w, -h), (w, h), (-w, h))]
        d.polygon(pts, fill=p["c"] + (255,))

def icon(d, kind, cx, cy, col):
    if kind == "bars":
        for i, h in enumerate((40, 70, 100, 130)):
            x = cx - 72 + i * 38
            d.rounded_rectangle((x, cy + 65 - h, x + 26, cy + 65), 8, fill=col if i < 3 else (255, 255, 255, 110))
    elif kind == "bulb":
        d.ellipse((cx - 50, cy - 70, cx + 50, cy + 30), fill=col)
        d.rounded_rectangle((cx - 26, cy + 26, cx + 26, cy + 62), 8, fill=(255, 255, 255, 230))
        for k in range(5):
            a = math.radians(-160 + k * 35)
            d.line((cx + math.cos(a) * 70, cy - 20 + math.sin(a) * 70, cx + math.cos(a) * 92, cy - 20 + math.sin(a) * 92), fill=col, width=7)
    else:  # calendar
        d.rounded_rectangle((cx - 66, cy - 56, cx + 66, cy + 66), 16, fill=(255, 255, 255, 235))
        d.rounded_rectangle((cx - 66, cy - 56, cx + 66, cy - 16), 16, fill=col)
        for k in (-34, 34): d.rounded_rectangle((cx + k - 6, cy - 76, cx + k + 6, cy - 40), 5, fill=(255, 255, 255))
        d.text((cx, cy + 26), "1", font=font(F_BODY, 60, 900), fill=col, anchor="mm")

FEATURES = [("٤ مستويات صعوبة", "من المبتدئ لحد الخبير", "bars", CYAN),
            ("تلميحات ذكية", "لما تعلق.. نديك الخيط", "bulb", GOLD),
            ("تحدّي يومي جديد", "وسلسلة انتصارات تكبر", "cal", PINK)]

def scene_features(t):  # 12 – 17
    img = gradient((10, 18, 48), (40, 16, 70), (20, 80, 160)).copy()
    particles(img, t + 12, (180, 200, 255))
    a = prog(t, 0, .4)
    txt(img, "ليه هتحبها؟", 540, 330, 150, F_HEAD, WHITE, lerp(.3, 1, ease_back(a)), a, glow=PINK, rot=lerp(-12, 0, ease_out(a)))
    for i, (title, sub, ic, col) in enumerate(FEATURES):
        p = prog(t, .45 + i * .75, 1.05 + i * .75)
        if not p: continue
        e = ease_back(p, 1.4)
        side = 1 if i % 2 == 0 else -1
        cy = 700 + i * 360
        cx = 540 + side * (1 - e) * 1200
        card = Image.new("RGBA", (920, 300), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        cd.rounded_rectangle((0, 0, 919, 299), 48, fill=(255, 255, 255, 34), outline=col + (200,), width=4)
        cd.ellipse((40, 60, 220, 240), fill=col + (60,))
        icon(cd, ic, 130, 150, col + (255,))
        tl = text_layer(title, F_HEAD, 84, WHITE)
        card.alpha_composite(tl, (860 - tl.width + 60, 40 - 30))
        sl = text_layer(sub, F_BODY, 44, (215, 220, 245))
        card.alpha_composite(sl, (860 - sl.width + 60, 170 - 55))
        paste_center(img, card, cx, cy, 1, clamp(p * 2))
    z = lerp(1.0, 1.08, ease_in_out(prog(t, 0, 5))) * lerp(1.3, 1, ease_out(prog(t, 0, .4)))
    return camera(img, z, 540, 1000)

def scene_benefit(t):  # 17 – 20 : "5 minutes a day = sharper mind" with ZOOM OUT + rays
    img = gradient((255, 170, 60), (220, 60, 110), (255, 230, 150)).copy()
    rays = Image.new("RGBA", (W, H), (0, 0, 0, 0)); rd = ImageDraw.Draw(rays)
    for k in range(18):
        a0 = math.radians(k * 20 + t * 25)
        rd.polygon([(540, 980), (540 + math.cos(a0) * 2400, 980 + math.sin(a0) * 2400),
                    (540 + math.cos(a0 + .17) * 2400, 980 + math.sin(a0 + .17) * 2400)], fill=(255, 255, 255, 40))
    img.alpha_composite(rays)
    particles(img, t + 17, WHITE)
    mins = int(lerp(0, 5, ease_out(prog(t, .1, .8))))
    a = prog(t, .05, .4)
    txt(img, f"{mins}", 540, 640, 380, F_HEAD, WHITE, spring(a) if a else 0, a, glow=(255, 90, 0), stroke=0)
    txt(img, "دقايق في اليوم", 540, 900, 120, F_HEAD, NAVY, 1, prog(t, .4, .7))
    b = prog(t, .9, 1.2)
    txt(img, "=", 540, 1070, 150, F_HEAD, WHITE, spring(b) if b else 0, b)
    c = prog(t, 1.2, 1.55)
    txt(img, "تركيز أعلى", 540, 1240, 140, F_HEAD, WHITE, spring(c) if c else 0, c, glow=(160, 0, 60))
    e = prog(t, 1.5, 1.85)
    txt(img, "وذاكرة أقوى", 540, 1410, 140, F_HEAD, NAVY, spring(e) if e else 0, e)
    return camera(img, lerp(1.55, 1.0, ease_out(prog(t, 0, 2.6))), 540, 1000, rot=lerp(6, 0, ease_out(prog(t, 0, 1.2))))

def scene_end(t):  # 20 – 24 : logo + CTA
    img = gradient(NAVY, (30, 14, 60), (80, 50, 200)).copy()
    particles(img, t + 20, GOLD)
    d = ImageDraw.Draw(img)
    # 3x3 logo tiles fly in
    size, gap, lx, ly = 110, 14, 540, 640
    rnd = random.Random(3)
    for i in range(9):
        r, c = divmod(i, 3)
        p = ease_back(prog(t, .05 * i, .5 + .05 * i), 1.6)
        sx, sy = rnd.uniform(-500, 1500), rnd.choice((-400, 2300))
        tx = lx + (c - 1) * (size + gap); ty = ly + (r - 1) * (size + gap)
        x, y = lerp(sx, tx, p), lerp(sy, ty, p)
        col = GOLD if i == 4 else ((255, 255, 255) if (r + c) % 2 == 0 else (120, 170, 255))
        tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(tile).rounded_rectangle((0, 0, size - 1, size - 1), 24, fill=col + (255,))
        if i == 4:
            ImageDraw.Draw(tile).text((size / 2, size / 2 + 4), "9", font=font(F_BODY, 80, 900), fill=NAVY, anchor="mm")
        paste_center(img, tile, x, y, 1, clamp(p * 3), rot=(1 - p) * 180)
    a = prog(t, .8, 1.2)
    txt(img, "سودوكو", 540, 1030, 210, F_HEAD, WHITE, spring(a) if a else 0, a, glow=CYAN)
    b = prog(t, 1.2, 1.5)
    txt(img, "تمرين يومي لعقلك", 540, 1210, 72, F_BODY, (210, 215, 255), 1, b)
    c = prog(t, 1.6, 2.0)
    if c:
        pulse = 1 + .05 * math.sin((t - 1.6) * 8) if t > 2.0 else spring(c)
        btn = Image.new("RGBA", (760, 190), (0, 0, 0, 0))
        ImageDraw.Draw(btn).rounded_rectangle((0, 0, 759, 189), 95, fill=GOLD + (255,))
        bl = text_layer("حمّلها مجاناً", F_HEAD, 104, NAVY)
        btn.alpha_composite(bl, ((760 - bl.width) // 2, (190 - bl.height) // 2))
        halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        hr = 60 + 40 * ((t * 1.2) % 1)
        ImageDraw.Draw(halo).rounded_rectangle((540 - 380 - hr / 3, 1480 - 95 - hr / 3, 540 + 380 + hr / 3, 1480 + 95 + hr / 3), 120,
                                               outline=GOLD + (int(200 * (1 - (t * 1.2) % 1)),), width=6)
        img.alpha_composite(halo)
        paste_center(img, btn, 540, 1480, pulse, c)
    e = prog(t, 2.2, 2.6)
    txt(img, "Android  •  iOS", 540, 1700, 56, F_BODY, (180, 190, 230), 1, e)
    z = lerp(1.2, 1.0, ease_out(prog(t, 0, 1.4)))
    return camera(img, z, 540, 1000)

SCENES = [(0, 3.5, scene_hook), (3.5, 6.0, scene_problem), (6.0, 12.0, scene_grid),
          (12.0, 17.0, scene_features), (17.0, 20.0, scene_benefit), (20.0, 24.0, scene_end)]
CUTS = [s for s, _, _ in SCENES[1:]]

GRAIN = [Image.fromarray(np.random.normal(0, 7, (H // 2, W // 2)).clip(-20, 20).astype(np.int16).__add__(128).astype(np.uint8)).resize((W, H)).convert("L") for _ in range(4)]

def frame(t):
    for s, e, fn in SCENES:
        if s <= t < e or (fn is scene_end and t >= s):
            img = fn(t - s); break
    arr = np.asarray(img.convert("RGB")).astype(np.float32)
    arr *= VIGNETTE
    g = np.asarray(GRAIN[int(t * FPS) % 4], np.float32)[..., None] - 128
    arr += g
    # flash on cuts + fade in/out
    for c in CUTS:
        dt = t - c
        if 0 <= dt < .18: arr += 255 * (1 - dt / .18) * .6
    fade = min(prog(t, 0, .35), 1 - prog(t, DUR - .5, DUR))
    arr *= fade
    return np.clip(arr, 0, 255).astype(np.uint8)

# ================================================================= AUDIO
def synth_audio():
    n = int(SR * DUR); tt = np.arange(n) / SR
    mix = np.zeros(n); bpm = 120; beat = 60 / bpm
    def add(sig, at, gain=1.0):
        i = int(at * SR); j = min(n, i + len(sig))
        if i < n: mix[i:j] += sig[:j - i] * gain
    def env(L, a=.005, r=.2):
        x = np.arange(int(L * SR)) / SR
        return np.minimum(1, x / a) * np.exp(-x / r)
    def note(f, L, kind="saw", a=.01, r=.3):
        x = np.arange(int(L * SR)) / SR
        if kind == "sine": w = np.sin(2 * np.pi * f * x)
        elif kind == "tri": w = 2 * np.abs(2 * ((f * x) % 1) - 1) - 1
        else: w = sum(np.sin(2 * np.pi * f * k * x) / k for k in range(1, 9)) * .6
        return w * env(L, a, r)
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    kick = lambda: np.sin(2 * np.pi * np.cumsum(50 + 110 * np.exp(-np.arange(int(.35 * SR)) / SR / .04)) / SR) * env(.35, .001, .12)
    snare = lambda: (np.random.randn(int(.25 * SR)) * .6 + np.sin(2 * np.pi * 190 * np.arange(int(.25 * SR)) / SR) * .5) * env(.25, .001, .07)
    hat = lambda: np.diff(np.random.randn(int(.06 * SR) + 1)) * env(.06, .001, .015)
    # chords (vi IV I V) in C:  Am F C G
    prog_ch = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]
    bass = [45, 41, 48, 43]
    # --- intro 0-6s: tense pad + ticking, riser
    for k in range(12):
        add(np.sin(2 * np.pi * 2200 * np.arange(int(.03 * SR)) / SR) * env(.03, .001, .008), k * .5, .18)
    pad = sum(note(hz(m), 6.0, "tri", 1.5, 9) for m in (45, 52, 57, 60))
    add(pad * np.linspace(1, .6, len(pad)), 0, .08)
    add(np.sin(2 * np.pi * np.cumsum(np.linspace(55, 55, int(3.5 * SR))) / SR) * .0 , 0)
    # low hits at 3.5 (problem scene) and 4.85
    for at in (3.5, 3.85):
        add(kick(), at, .9); add(note(hz(33), 1.2, "sine", .005, .5), at, .5)
    riser_len = 1.6; x = np.arange(int(riser_len * SR)) / SR
    riser = np.random.randn(len(x)) * (x / riser_len) ** 2
    riser = np.convolve(riser, np.ones(12) / 12, "same") + .3 * np.sin(2 * np.pi * np.cumsum(300 + 1800 * (x / riser_len) ** 2) / SR) * (x / riser_len)
    add(riser, 6.0 - riser_len, .35)
    # --- drop 6s - 22s: full groove
    start, end = 6.0, 22.0
    b = 0
    tpos = start
    while tpos < end - 1e-6:
        bar = int((tpos - start) / (4 * beat)) % 4
        pos = int(round((tpos - start) / beat)) % 4
        add(kick(), tpos, .95)
        if pos in (1, 3): add(snare(), tpos, .45)
        add(hat(), tpos + beat / 2, .25); add(hat(), tpos, .12)
        # bass pulsing 8ths
        for h in (0, .5):
            add(note(hz(bass[bar]), beat / 2, "saw", .005, .12), tpos + h * beat, .22)
        # pluck arpeggio 16ths
        ch = prog_ch[bar]
        for s16 in range(4):
            m = ch[(pos * 4 + s16) % 3] + 12 + (12 if s16 == 3 else 0)
            add(note(hz(m), .2, "tri", .002, .08), tpos + s16 * beat / 4, .09)
        if pos == 0:
            pd = sum(note(hz(m), 4 * beat, "saw", .08, 1.2) for m in ch)
            add(pd, tpos, .035)
        tpos += beat
    # final chord + tail
    fin = sum(note(hz(m), 2.5, "saw", .005, 1.0) for m in (48, 55, 60, 64, 67))
    add(fin, 22.0, .07); add(kick(), 22.0, 1.0)
    # --- SFX synced to visuals
    def whoosh(L=.45):
        x = np.arange(int(L * SR)) / SR
        nse = np.random.randn(len(x))
        k = int(20 + 60 * 1)
        nse = nse - np.convolve(nse, np.ones(k) / k, "same")
        return nse * np.sin(np.pi * x / L) ** 2
    for c in (3.5, 6.0, 12.0, 17.0, 20.0): add(whoosh(), c - .2, .25)
    pop = lambda f: np.sin(2 * np.pi * np.cumsum(np.linspace(f * 1.6, f, int(.08 * SR))) / SR) * env(.08, .001, .03)
    for i in range(0, len(GIVEN_ORDER), 3): add(pop(900 + (i % 7) * 60), 6.6 + i * .03, .12)
    add(pop(1400), 9.25, .4); add(note(hz(84), .6, "sine", .002, .25), 9.25, .2); add(note(hz(91), .6, "sine", .002, .25), 9.33, .2)
    for i in range(0, len(EMPTY), 4): add(pop(1100 + (i % 5) * 90), 9.7 + i / len(EMPTY) * 1.0, .07)
    for k, m in enumerate((72, 76, 79, 84)): add(note(hz(m), .5, "tri", .002, .2), 11.0 + k * .07, .18)
    for k in range(3): add(whoosh(.35), 12.45 + k * .75, .18)
    for k in range(9): add(pop(700 + k * 50), 20.05 * 1 + k * .05, .06)
    # master: sidechain-ish pump + soft clip
    pump = np.ones(n)
    tb = start
    while tb < end:
        i = int(tb * SR); L = int(.18 * SR)
        pump[i:i + L] = np.minimum(pump[i:i + L], .55 + .45 * np.linspace(0, 1, len(pump[i:i + L])))
        tb += beat
    mix *= pump
    mix = np.tanh(mix * 1.4) * .85
    fade = np.minimum(1, np.minimum(tt / .05, (DUR - tt) / 1.2))
    mix *= np.clip(fade, 0, 1)
    st = np.stack([mix, np.roll(mix, 220) * .96 + mix * .04], 1)  # tiny stereo width
    path = os.path.join(OUT, "music.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((st * 32767).astype(np.int16).tobytes())
    return path

# ================================================================= main
def main():
    if "--preview" in sys.argv:
        for t in (1.5, 4.8, 7.3, 8.9, 10.2, 11.5, 15.5, 18.8, 23.0):
            Image.fromarray(frame(t)).resize((360, 640)).save(os.path.join(OUT, f"prev_{t:05.1f}.png"))
        return
    audio = synth_audio()
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    out = os.path.join(OUT, "sudoku_ad.mp4")
    p = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", audio, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out],
                         stdin=subprocess.PIPE)
    total = int(DUR * FPS)
    for i in range(total):
        p.stdin.write(frame(i / FPS).tobytes())
        if i % 60 == 0: print(f"frame {i}/{total}", flush=True)
    p.stdin.close(); p.wait()
    print("wrote", out)

if __name__ == "__main__":
    main()
