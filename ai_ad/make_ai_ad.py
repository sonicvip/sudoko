"""AI promo for TikTok — 1080x1920 @30fps, ~58s.

Visuals : 8 AI-generated stills (assets/img) with Ken Burns camera, bloom, light
          leaks, HUD, kinetic Arabic headlines, captions and 5 transition types.
Audio   : Arabic voice-over (assets/vo.mp3) auto-split on its pauses and laid out
          on the timeline + a synthesized cinematic score and SFX with ducking.

Usage:  python3 make_ai_ad.py            -> out/ai_ad.mp4
        python3 make_ai_ad.py --preview  -> out/contact.png (stills contact sheet)
"""
import math, os, random, re, subprocess, sys, wave
from functools import lru_cache
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
W, H, FPS, SR = 1080, 1920, 30, 44100
TARGET_DUR = 58.0
FF = imageio_ffmpeg.get_ffmpeg_exe()
rng = np.random.default_rng(11)
random.seed(11)

WHITE = (255, 255, 255)
CYAN = (70, 225, 255)
VIOLET = (170, 110, 255)
GOLD = (255, 200, 90)
RED = (255, 80, 90)
INK = (8, 10, 22)

# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def prog(t, a, b): return clamp((t - a) / (b - a)) if b > a else float(t >= a)
def ease_out(x): return 1 - (1 - x) ** 3
def ease_in(x): return x ** 3
def ease_io(x): return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2
def ease_back(x, s=1.7): x -= 1; return 1 + (s + 1) * x ** 3 + s * x ** 2
def lerp(a, b, x): return a + (b - a) * x

# ================================================================ VOICE-OVER
# The VO file is one take of these lines (one per scene), in order.
LINES = [
    "إنت لسه فاكر إن الذكاء الاصطناعي حاجة جاية في المستقبل؟ المستقبل ده بدأ خلاص.",
    "الموبايل اللي في إيدك بقى بيكتب، وبيرسم، وبيترجم، وبيتكلم.",
    "الدكاترة بيكتشفوا الأمراض قبل ما تظهر،",
    "والمهندسين بيصمموا مدن كاملة في ساعات بدل سنين.",
    "وفي ناس بتبني مشاريع كاملة لوحدها، من غير فريق، ومن غير رأس مال.",
    "بس خد بالك: الـ AI مش هياخد شغلك. اللي هياخد شغلك، واحد بيعرف يستخدم الـ AI أحسن منك.",
    "والخبر الحلو؟ إنك لسه في الأول. ابدأ النهارده، اتعلم أداة واحدة كل أسبوع،",
    "وبعد سنة، هتبقى شخص تاني خالص. تابعنا، لأن المستقبل مش بيستنى حد.",
]
N = len(LINES)

def decode(path):
    raw = subprocess.run([FF, "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)

def silences(path):
    err = subprocess.run([FF, "-hide_banner", "-i", path, "-af", "silencedetect=noise=-33dB:d=0.16", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    s = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    e = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    return list(zip(s, e))

def split_vo():
    """Cut the VO into one piece per scene at the pause nearest the expected boundary."""
    path = os.path.join(ASSETS, "vo.mp3")
    if not os.path.exists(path):  # dry run: silent stand-in with plausible timing
        lens = [len(l) for l in LINES]
        return [np.zeros(int(SR * 40.0 * n / sum(lens))) for n in lens], False
    vo = decode(path)
    total = len(vo) / SR
    sil = silences(path)
    lens = np.cumsum([len(l) for l in LINES]); lens = lens / lens[-1]
    cuts, last = [0.0], 0.0
    for k in range(N - 1):
        exp = total * lens[k]
        best = min((s for s in sil if (s[0] + s[1]) / 2 > last + .5),
                   key=lambda s: 0 if s[0] <= exp <= s[1] else min(abs(s[0] - exp), abs(s[1] - exp)), default=None)
        c = (best[0] + best[1]) / 2 if best and abs((best[0] + best[1]) / 2 - exp) < 3.0 else exp
        cuts.append(c); last = c
    cuts.append(total)
    pieces = []
    thr = 10 ** (-38 / 20) * np.max(np.abs(vo))
    for a, b in zip(cuts, cuts[1:]):
        p = vo[int(a * SR):int(b * SR)]
        loud = np.nonzero(np.abs(p) > thr)[0]
        if len(loud):
            p = p[max(0, loud[0] - int(.04 * SR)):min(len(p), loud[-1] + int(.12 * SR))]
        pieces.append(p)
    return pieces, True

PIECES, HAVE_VO = split_vo()
SPEECH = [len(p) / SR for p in PIECES]
INTRO, OUTRO = 0.7, 4.2
GAP = clamp((TARGET_DUR - INTRO - OUTRO - sum(SPEECH)) / (N - 1), 0.9, 1.9)
SP_START, t = [], INTRO
for L in SPEECH:
    SP_START.append(t); t += L + GAP
DUR = SP_START[-1] + SPEECH[-1] + OUTRO
# scene k spans [START[k], START[k+1]) ; the cut sits a bit before the next line
START = [0.0] + [SP_START[k] - GAP * .42 for k in range(1, N)] + [DUR]

def at(k, word, occurrence=0):
    """Global time where `word` is spoken inside scene k's line (char-proportional)."""
    line, i = LINES[k], -1
    for _ in range(occurrence + 1): i = LINES[k].find(word, i + 1)
    i = max(i, 0)
    return SP_START[k] + SPEECH[k] * (i / len(line)) * .96

# ================================================================ FONTS / TEXT
F_HEAD = os.path.join(ASSETS, "Lalezar.ttf")
F_BODY = os.path.join(ASSETS, "Cairo.ttf")

@lru_cache(None)
def font(path, size):
    f = ImageFont.truetype(path, size)
    if path == F_BODY:
        try:
            f.set_variation_by_axes([800])
        except Exception:
            pass
    return f

@lru_cache(None)
def text_layer(text, size, color=WHITE, path=F_HEAD, glow=None, stroke=0, box=None, pad=(38, 16)):
    """RGBA numpy layer (float32 0..1) of a text line with optional glow and pill box."""
    f = font(path, size)
    kw = dict(direction="rtl", language="ar") if re.search("[؀-ۿ]", text) else {}
    x0, y0, x1, y1 = f.getbbox(text, stroke_width=stroke, **kw)
    m = 50
    bw, bh = x1 - x0 + 2 * pad[0], y1 - y0 + 2 * pad[1]
    im = Image.new("RGBA", (bw + 2 * m, bh + 2 * m), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if box:
        d.rounded_rectangle((m, m, m + bw, m + bh), radius=bh // 2, fill=box)
    d.text((m + pad[0] - x0, m + pad[1] - y0), text, font=f, fill=color + (255,),
           stroke_width=stroke, stroke_fill=(0, 0, 0, 200), **kw)
    if glow:
        g = Image.new("RGBA", im.size, glow + (0,))
        g.putalpha(im.getchannel("A").filter(ImageFilter.GaussianBlur(size / 5)))
        im = Image.alpha_composite(Image.alpha_composite(g, g), im)
    return np.asarray(im, np.float32) / 255.0

def scaled(layer, s):
    if abs(s - 1) < .01: return layer
    h, w = layer.shape[:2]
    im = Image.fromarray((layer * 255).astype(np.uint8), "RGBA")
    im = im.resize((max(2, int(w * s)), max(2, int(h * s))), Image.BILINEAR)
    return np.asarray(im, np.float32) / 255.0

def blit(arr, layer, cx, cy, alpha=1.0, scale=1.0, rgb_split=0):
    """Alpha-composite an RGBA float layer centred at (cx, cy) onto arr (float 0..255)."""
    if alpha <= .005 or scale <= .02: return
    L = scaled(layer, scale)
    h, w = L.shape[:2]
    x, y = int(cx - w / 2), int(cy - h / 2)
    xa, ya, xb, yb = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if xa >= xb or ya >= yb: return
    sub = L[ya - y:yb - y, xa - x:xb - x]
    a = sub[..., 3:4] * alpha
    dst = arr[ya:yb, xa:xb]
    if rgb_split:
        o = int(rgb_split)
        rgb = sub[..., :3].copy()
        rgb[..., 0] = np.roll(sub[..., 0], o, 1); rgb[..., 2] = np.roll(sub[..., 2], -o, 1)
        a = np.maximum(a, np.roll(a, o, 1) * .6)
        dst[:] = dst * (1 - a) + rgb * 255 * a
    else:
        dst[:] = dst * (1 - a) + sub[..., :3] * 255 * a

# ================================================================ IMAGES
IMG_FILES = ["01_eye", "02_phone", "03_doctor", "04_city", "05_founder", "06_robot", "07_portal", "08_sunrise"]
K = 1.22  # supersample margin for camera moves

def placeholder(name, i):
    hue = [(20, 60, 140), (80, 30, 140), (10, 110, 120), (140, 100, 20), (20, 50, 110), (120, 40, 40), (70, 30, 150), (160, 90, 20)][i]
    yy, xx = np.mgrid[0:640, 0:360].astype(np.float32)
    g = np.exp(-(((xx - 180) / 160) ** 2 + ((yy - 300) / 260) ** 2))[..., None]
    a = np.array(hue, np.float32) * (.25 + 1.2 * g)
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    ImageDraw.Draw(im).text((20, 20), name, fill=(255, 255, 255))
    return im

def load(i):
    name = IMG_FILES[i]
    p = next((os.path.join(ASSETS, "img", name + e) for e in (".png", ".jpg", ".jpeg", ".webp")
              if os.path.exists(os.path.join(ASSETS, "img", name + e))), None)
    im = Image.open(p).convert("RGB") if p else placeholder(name, i)
    s = max(W / im.width, H / im.height) * K
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    if p: im = im.filter(ImageFilter.UnsharpMask(2, 60, 2))
    return im

IMGS = [load(i) for i in range(N)]

def camera(k, zoom, dx=0.0, dy=0.0, rot=0.0):
    """Render scene image k with zoom (>=1) and pan offset in output pixels."""
    im = IMGS[k]
    cw, ch = im.width / K, im.height / K
    lim_x = max(0.0, cw / 2 - W / (2 * zoom)); lim_y = max(0.0, ch / 2 - H / (2 * zoom))
    dx, dy = clamp(dx, -lim_x, lim_x), clamp(dy, -lim_y, lim_y)
    s = K / zoom
    ca, sa = math.cos(math.radians(rot)) * s, math.sin(math.radians(rot)) * s
    cx, cy = K * (cw / 2 + dx), K * (ch / 2 + dy)
    data = (ca, sa, cx - ca * W / 2 - sa * H / 2, -sa, ca, cy + sa * W / 2 - ca * H / 2)
    return np.asarray(im.transform((W, H), Image.AFFINE, data, resample=Image.BILINEAR), np.float32)

# Ken Burns per scene: zoom from->to, pan from->to (output px)
KB = [
    (1.35, 1.05, (0, 0), (0, 0)),        # eye: slow pull-out
    (1.05, 1.22, (0, 60), (0, -40)),     # phone: push in, rise
    (1.18, 1.06, (60, 0), (-50, 0)),     # doctor: drift right->left
    (1.06, 1.25, (0, 40), (0, -60)),     # city: push in
    (1.20, 1.08, (-40, -30), (40, 20)),  # founder
    (1.08, 1.30, (0, 0), (0, 0)),        # robot: slow tense push
    (1.10, 1.32, (0, 80), (0, -20)),     # portal: fly toward the light
    (1.28, 1.06, (30, 60), (0, 0)),      # sunrise: reveal
]

# ================================================================ FX LAYERS
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
_r = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2)
VIGNETTE = np.clip(1.22 - _r * 1.3, 0.28, 1.0)[..., None].astype(np.float32)
GRAIN = [rng.normal(0, 4.5, (H // 2, W // 2)).astype(np.float32) for _ in range(6)]
del _r

def grain(i):
    g = GRAIN[i % 6]
    return np.repeat(np.repeat(g, 2, 0), 2, 1)[..., None]

def bloom(arr, amount=.38):
    small = Image.fromarray(np.clip(arr[::6, ::6], 0, 255).astype(np.uint8))
    s = np.asarray(small, np.float32)
    s = np.clip(s - 150, 0, 255) * 1.6
    b = Image.fromarray(s.astype(np.uint8)).filter(ImageFilter.GaussianBlur(10)).resize((W, H), Image.BILINEAR)
    return arr + np.asarray(b, np.float32) * amount

@lru_cache(None)
def leak_sprite(color, rx, ry):
    h, w = int(ry * 2), int(rx * 2)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    g = np.exp(-(((x - rx) / (rx * .5)) ** 2 + ((y - ry) / (ry * .5)) ** 2))
    return g[..., None] * np.array(color, np.float32)

def add_sprite(arr, spr, cx, cy, gain):
    h, w = spr.shape[:2]
    x, y = int(cx - w / 2), int(cy - h / 2)
    xa, ya, xb, yb = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if xa < xb and ya < yb:
        arr[ya:yb, xa:xb] += spr[ya - y:yb - y, xa - x:xb - x] * gain

def light_leak(arr, t, color, gain=.35):
    add_sprite(arr, leak_sprite(color, 700, 900), W * (.15 + .7 * (.5 + .5 * math.sin(t * .35))), H * .25, gain)
    add_sprite(arr, leak_sprite(color, 500, 700), W * (.85 - .6 * (.5 + .5 * math.sin(t * .27 + 1))), H * .85, gain * .6)

PARTS = [dict(x=random.uniform(0, W), y=random.uniform(0, H), s=random.uniform(1.5, 5), v=random.uniform(15, 70),
              ph=random.uniform(0, 6.28)) for _ in range(55)]

@lru_cache(None)
def dot(r, color):
    n = int(r * 4) + 2
    y, x = np.mgrid[0:n, 0:n].astype(np.float32) - n / 2
    return np.exp(-(x * x + y * y) / (r * r))[..., None] * np.array(color, np.float32)

def particles(arr, t, color, gain=.9):
    for p in PARTS:
        y = (p["y"] - p["v"] * t) % H
        x = p["x"] + 25 * math.sin(t * .7 + p["ph"])
        a = gain * (.45 + .55 * math.sin(t * 2.2 + p["ph"]) ** 2)
        add_sprite(arr, dot(round(p["s"] * 2) / 2, color), x, y, a)

def hud(arr, t, color, a=1.0):
    """Thin corner brackets + scanning line: 'premium tech' framing."""
    c = np.array(color, np.float32)
    m, L, th = 70, 90, 4
    for (x0, y0, sx, sy) in ((m, m + 60, 1, 1), (W - m, m + 60, -1, 1), (m, H - m - 260, 1, -1), (W - m, H - m - 260, -1, -1)):
        xs = sorted((x0, x0 + sx * L)); ys = sorted((y0, y0 + sy * L))
        arr[y0 - th // 2 if sy > 0 else y0 - th // 2:y0 + th // 2, xs[0]:xs[1]] = arr[y0 - th // 2:y0 + th // 2, xs[0]:xs[1]] * (1 - .8 * a) + c * .8 * a
        arr[ys[0]:ys[1], x0 - th // 2:x0 + th // 2] = arr[ys[0]:ys[1], x0 - th // 2:x0 + th // 2] * (1 - .8 * a) + c * .8 * a

def scanline(arr, t, color, speed=.55, a=.5):
    y = int((t * speed % 1) * H)
    band = np.exp(-((np.arange(-60, 60, dtype=np.float32)) / 22) ** 2)[:, None, None] * np.array(color, np.float32) * a
    ya, yb = max(0, y - 60), min(H, y + 60)
    arr[ya:yb] += band[ya - (y - 60):yb - (y - 60)]
    arr[max(0, y - 1):y + 1] += np.array(color, np.float32) * a * 1.3

def glitch(arr, amount, seed):
    if amount <= .01: return arr
    r = np.random.default_rng(seed)
    out = arr.copy()
    o = int(28 * amount)
    out[..., 0] = np.roll(arr[..., 0], o, 1); out[..., 2] = np.roll(arr[..., 2], -o, 1)
    for _ in range(int(9 * amount) + 1):
        y = r.integers(0, H - 80); h = r.integers(10, 120)
        out[y:y + h] = np.roll(out[y:y + h], int(r.integers(-160, 160) * amount), 1)
    return out

def hblur(arr, k):
    k = int(k)
    if k < 3: return arr
    c = np.cumsum(np.pad(arr, ((0, 0), (k // 2 + 1, k // 2), (0, 0)), mode="edge"), axis=1)
    return (c[:, k:] - c[:, :-k])[:, :W] / k

# ================================================================ SCENE CONTENT
# headline item: (time, text, y, size, color, style, extra)
def headlines(k):
    Y = 470
    if k == 0: return [
        (at(0, "الذكاء"), "الذكاء الاصطناعي", Y - 60, 118, CYAN, "glitch", {"until": at(0, "المستقبل", 1) - .1}),
        (at(0, "حاجة"), "حاجة جاية؟", Y + 90, 92, WHITE, "pop", {"until": at(0, "المستقبل", 1) - .1}),
        (at(0, "المستقبل", 1), "المستقبل", Y - 40, 150, WHITE, "slam", {}),
        (at(0, "بدأ"), "بدأ خلاص.", Y + 130, 170, GOLD, "slam", {}),
    ]
    if k == 1: return [
        (at(1, "بيكتب"), "بيكتب", Y - 110, 120, WHITE, "chip", {}),
        (at(1, "وبيرسم"), "بيرسم", Y + 40, 120, WHITE, "chip", {}),
        (at(1, "وبيترجم"), "بيترجم", Y + 190, 120, WHITE, "chip", {}),
        (at(1, "وبيتكلم"), "بيتكلم", Y + 340, 120, CYAN, "chip", {}),
    ]
    if k == 2: return [
        (at(2, "الدكاترة"), "يكتشف المرض", Y - 30, 130, WHITE, "pop", {}),
        (at(2, "قبل"), "قبل ما يظهر", Y + 120, 140, CYAN, "slam", {}),
    ]
    if k == 3: return [
        (at(3, "مدن"), "مدن كاملة", Y - 40, 140, WHITE, "pop", {}),
        (at(3, "ساعات"), "في ساعات", Y + 110, 130, GOLD, "slam", {}),
        (at(3, "سنين"), "مش سنين", Y + 250, 100, (200, 200, 210), "strike", {}),
    ]
    if k == 4: return [
        (at(4, "مشاريع"), "مشروع كامل", Y - 60, 130, WHITE, "pop", {}),
        (at(4, "لوحدها"), "لوحدك.", Y + 90, 170, CYAN, "slam", {}),
        (at(4, "فريق"), "×  من غير فريق", Y + 250, 70, WHITE, "chip", {"font": F_BODY}),
        (at(4, "رأس"), "×  من غير رأس مال", Y + 360, 70, WHITE, "chip", {"font": F_BODY}),
    ]
    if k == 5: return [
        (at(5, "الـ AI"), "الـ AI", Y - 120, 150, CYAN, "glitch", {"until": at(5, "واحد") - .1}),
        (at(5, "مش"), "مش هياخد شغلك", Y + 40, 120, WHITE, "slam", {"until": at(5, "واحد") - .1}),
        (at(5, "واحد"), "اللي هياخده", Y - 100, 110, WHITE, "pop", {}),
        (at(5, "يستخدم"), "واحد بيستخدمه", Y + 40, 125, GOLD, "slam", {}),
        (at(5, "أحسن"), "أحسن منك", Y + 190, 150, GOLD, "slam", {}),
    ]
    if k == 6: return [
        (at(6, "إنك"), "لسه في الأول", Y - 40, 150, WHITE, "slam", {"until": at(6, "ابدأ") - .1}),
        (at(6, "ابدأ"), "ابدأ النهارده", Y - 80, 140, CYAN, "slam", {}),
        (at(6, "أداة"), "أداة واحدة كل أسبوع", Y + 80, 88, WHITE, "chip", {}),
    ]
    if k == 7: return [
        (at(7, "سنة"), "بعد سنة…", Y - 100, 110, WHITE, "pop", {"until": at(7, "تابعنا") - .15}),
        (at(7, "شخص"), "شخص تاني خالص", Y + 50, 140, GOLD, "slam", {"until": at(7, "تابعنا") - .15}),
    ]
    return []

HEAD = [headlines(k) for k in range(N)]
SHAKES = [h[0] for hs in HEAD for h in hs if h[5] == "slam"]

def draw_headlines(arr, k, t):
    for (t0, text, y, size, color, style, ex) in HEAD[k]:
        if t < t0 - .02: continue
        dt = t - t0
        until = ex.get("until")
        out = 1.0 if until is None else 1 - prog(t, until, until + .22)
        if out <= 0: continue
        path = ex.get("font", F_HEAD)
        glow = color if color != WHITE else (120, 170, 255)
        if style == "chip":
            layer = text_layer(text, size, WHITE if color == WHITE else INK, path,
                               box=(10, 12, 30, 170) if color == WHITE else color + (235,))
            p = ease_back(prog(dt, 0, .38))
            blit(arr, layer, W / 2 + (1 - p) * 140, y, alpha=min(1, dt / .15) * out, scale=.85 + .15 * p)
            continue
        layer = text_layer(text, size, color, path, glow=glow, stroke=2)
        if style == "pop":
            p = ease_back(prog(dt, 0, .4))
            blit(arr, layer, W / 2, y + (1 - p) * 60, alpha=min(1, dt / .18) * out, scale=.7 + .3 * p)
        elif style == "slam":
            p = ease_out(prog(dt, 0, .22))
            blit(arr, layer, W / 2, y, alpha=min(1, dt / .08) * out, scale=lerp(2.1, 1.0, p) * (1 - .04 * out * 0))
        elif style == "glitch":
            j = max(0, 1 - dt / .45)
            jx = (random.Random(int(t * 30)).uniform(-1, 1) * 30 * j)
            blit(arr, layer, W / 2 + jx, y, alpha=min(1, dt / .1) * out, rgb_split=16 * j + 3)
        elif style == "strike":
            p = ease_out(prog(dt, 0, .3))
            blit(arr, layer, W / 2, y, alpha=p * out * .9)
            s = ease_io(prog(dt, .25, .55))
            if s > 0:
                half = layer.shape[1] * .36
                x1, x0 = int(W / 2 + half), int(W / 2 + half - 2 * half * s)
                arr[int(y) - 4:int(y) + 5, x0:x1] = arr[int(y) - 4:int(y) + 5, x0:x1] * .2 + np.array(RED, np.float32) * .8

def cta(arr, t):
    """End card: follow button + tagline."""
    t0 = at(7, "تابعنا")
    if t < t0: return
    dt = t - t0
    a = ease_out(prog(dt, 0, .5))
    arr *= 1 - .45 * a  # darken for legibility
    blit(arr, text_layer("تابعنا", 190, WHITE, glow=CYAN, stroke=2), W / 2, 560, alpha=a, scale=lerp(1.6, 1, ease_out(prog(dt, 0, .3))))
    p = ease_back(prog(dt, .35, .8))
    pulse = 1 + .05 * math.sin(max(0, dt - .9) * 7) * (dt > .9)
    blit(arr, text_layer("+  متابعة", 92, WHITE, F_BODY, box=(254, 44, 85, 255), pad=(70, 22)), W / 2, 790,
         alpha=min(1, p * 1.5), scale=(.6 + .4 * p) * pulse)
    t2 = t0 + SPEECH[7] * .45
    if t > t2:
        q = ease_out(prog(t, t2, t2 + .5))
        blit(arr, text_layer("المستقبل مش بيستنى حد", 96, GOLD, glow=GOLD, stroke=2), W / 2, 1010 + (1 - q) * 40, alpha=q)
    # tap animation on the button
    tap = prog(dt, 1.4, 1.9)
    if 0 < tap < 1:
        r = 40 + 120 * tap
        add_sprite(arr, dot(r / 2, (255, 255, 255)), W / 2 + 150, 800, .55 * (1 - tap))

SCENE_COLOR = [CYAN, VIOLET, CYAN, GOLD, CYAN, RED, VIOLET, GOLD]

def scene(k, t, extra_zoom=1.0, extra_dx=0.0, frame_i=0):
    """Full frame of scene k at global time t (float array HxWx3, 0..255)."""
    z0, z1, p0, p1 = KB[k]
    x = ease_io(prog(t, START[k] - .4, START[k + 1] + .4))
    zoom = lerp(z0, z1, x) * extra_zoom
    shake = 0.0
    for s in SHAKES:
        if START[k] - .3 <= s <= START[k + 1] and 0 <= t - s < .35:
            shake = max(shake, 1 - (t - s) / .35)
    dx = lerp(p0[0], p1[0], x) + extra_dx + shake * 14 * math.sin(t * 97)
    dy = lerp(p0[1], p1[1], x) + shake * 14 * math.cos(t * 83)
    arr = camera(k, zoom * (1 + .025 * shake), dx, dy)
    col = SCENE_COLOR[k]
    lt = t - START[k]
    # per-scene grade/fx
    if k == 0:  # opening: start from black, iris pulse on the hook
        arr *= ease_out(prog(t, 0.0, .5))
    if k == 2: scanline(arr, lt, CYAN, .45, .35)
    if k == 5:  # tension: desaturate a touch, periodic glitch
        g = arr.mean(2, keepdims=True); arr = arr * .75 + g * .25
    arr = bloom(arr, .32 if k != 7 else .45)
    light_leak(arr, t + k * 3, col, .16 if k not in (6, 7) else .26)
    particles(arr, t, col, .7)
    hud(arr, t, col, .55)
    draw_headlines(arr, k, t)
    if k == 7: cta(arr, t)
    if k == 5:
        gl = 0.0
        for g0 in (at(5, "الـ AI"), at(5, "واحد"), START[5] + .05):
            if 0 <= t - g0 < .3: gl = max(gl, 1 - (t - g0) / .3)
        if (int(t * 30) % 47) == 0: gl = max(gl, .35)
        arr = glitch(arr, gl, int(t * 30))
    return arr

# ================================================================ TRANSITIONS
TRANS = ["zoom", "whip", "flash", "zoom", "whip", "glitch", "flash", "iris"]  # into scene k (k>=1)
TD = .5

def compose(t, i):
    k = next(j for j in range(N) if START[j] <= t < START[j + 1]) if t < DUR else N - 1
    # are we near a cut?
    for b in range(1, N):
        c = START[b]
        if abs(t - c) < TD / 2:
            p = (t - (c - TD / 2)) / TD  # 0..1
            kind = TRANS[b]
            if kind == "zoom":
                if p < .5:
                    q = ease_in(p * 2)
                    a = sum(scene(b - 1, t, 1 + q * (.35 + .06 * j)) for j in range(3)) / 3
                else:
                    q = 1 - ease_out((p - .5) * 2)
                    a = sum(scene(b, t, 1 + q * (.4 + .06 * j)) for j in range(3)) / 3
                a += 255 * max(0, 1 - abs(p - .5) / .18) * .55
                return a
            if kind == "whip":
                q = ease_io(p)
                off = q * W
                if p < .5:
                    a = scene(b - 1, t, 1.0, off * .9)
                else:
                    a = scene(b, t, 1.0, -(W - off) * .9)
                return hblur(a, 260 * math.sin(math.pi * p) + 1)
            if kind == "flash":
                A, B = scene(b - 1, t), scene(b, t)
                q = ease_io(p)
                m = A * (1 - q) + B * q
                w = max(0, 1 - abs(p - .5) / .5)
                return m + np.array((255, 230, 190), np.float32) * w ** 2 * .9
            if kind == "glitch":
                a = scene(b - 1, t) if p < .5 else scene(b, t)
                return glitch(a, 1 - abs(p - .5) * 2, i)
            if kind == "iris":
                A, B = scene(b - 1, t), scene(b, t)
                r = ease_io(p) * 1.25 * math.hypot(W, H) / 2
                d = np.sqrt((xx - W / 2) ** 2 + (yy - H * .45) ** 2)
                mk = np.clip((r - d) / 60, 0, 1)[..., None]
                ring = np.exp(-((d - r) / 14) ** 2)[..., None] * np.array(GOLD, np.float32) * .9
                return A * (1 - mk) + B * mk + ring
    return scene(k, t, frame_i=i)

# ================================================================ CAPTIONS
def chunks(k):
    words = LINES[k].split()
    out, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= 3 or w[-1] in "،.?؟:":
            out.append(" ".join(cur)); cur = []
    if cur: out.append(" ".join(cur))
    total = sum(len(c) + 1 for c in out)
    t, res = SP_START[k], []
    for c in out:
        d = SPEECH[k] * (len(c) + 1) / total
        res.append((t, t + d, c.strip("،.:")))
        t += d
    return res

CAPS = [c for k in range(N) for c in chunks(k)]

def captions(arr, t):
    for (a, b, text) in CAPS:
        if a <= t < b + .15:
            p = ease_back(prog(t, a, a + .2))
            q = 1 - prog(t, b, b + .15)
            blit(arr, text_layer(text, 62, WHITE, F_BODY, box=(0, 0, 0, 150), pad=(34, 10)), W / 2, 1400,
                 alpha=min(p, q), scale=.9 + .1 * p)
            break

def frame(i):
    t = i / FPS
    arr = compose(t, i)
    if t < START[-2] + .3 or t < at(7, "تابعنا"):
        captions(arr, t)
    arr *= VIGNETTE
    arr += grain(i)
    # progress bar (retention cue)
    w = int(W * t / DUR)
    arr[14:22, :w] = arr[14:22, :w] * .2 + np.array(CYAN, np.float32) * .8
    arr *= min(1.0, (DUR - t) / .6)
    return np.clip(arr, 0, 255).astype(np.uint8)

# ================================================================ AUDIO
def synth_audio():
    n = int(SR * (DUR + .1)); tt = np.arange(n) / SR
    mus = np.zeros((n, 2)); sfx = np.zeros((n, 2)); vo = np.zeros(n)

    def add(buf, sig, at_, gain=1.0, pan=0.0):
        if sig.ndim == 1: sig = np.stack([sig * (1 - max(0, pan)), sig * (1 + min(0, pan))], 1)
        i = int(at_ * SR)
        if i < 0: sig = sig[-i:]; i = 0
        j = min(n, i + len(sig))
        if i < n and j > i: buf[i:j] += sig[:j - i] * gain

    def env(L, a=.005, r=.2):
        x = np.arange(int(L * SR)) / SR
        return np.minimum(1, x / a) * np.exp(-x / r)
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    def osc(f, L, kind="saw", det=0.0):
        x = np.arange(int(L * SR)) / SR
        if kind == "sine": return np.sin(2 * np.pi * f * x)
        if kind == "tri": return 2 * np.abs(2 * ((f * x) % 1) - 1) - 1
        w = sum(np.sin(2 * np.pi * f * (1 + det) * h * x) / h for h in range(1, 12))
        return w * .55
    def lowpass(sig, fc):
        F = np.fft.rfft(sig, axis=0); fr = np.fft.rfftfreq(len(sig), 1 / SR)
        F *= (1 / np.sqrt(1 + (fr / fc) ** 4))[:, None] if sig.ndim == 2 else 1 / np.sqrt(1 + (fr / fc) ** 4)
        return np.fft.irfft(F, len(sig), axis=0)
    def highpass(sig, fc):
        return sig - lowpass(sig, fc)

    kick = lambda: np.sin(2 * np.pi * np.cumsum(45 + 130 * np.exp(-np.arange(int(.45 * SR)) / SR / .035)) / SR) * env(.45, .001, .16)
    clap = lambda: highpass(rng.standard_normal(int(.3 * SR)), 900) * env(.3, .002, .09) * .8
    hat = lambda o=False: highpass(rng.standard_normal(int(.12 * SR)), 7000) * env(.12, .001, .05 if o else .018)
    def boom(L=3.0):
        x = np.arange(int(L * SR)) / SR
        s = np.sin(2 * np.pi * np.cumsum(30 + 70 * np.exp(-x / .12)) / SR) * np.exp(-x / .9)
        s += lowpass(rng.standard_normal(len(x)), 300) * np.exp(-x / .35) * .6
        return np.tanh(s * 1.5)
    def riser(L):
        x = np.arange(int(L * SR)) / SR; u = x / L
        s = highpass(rng.standard_normal(len(x)), 1500) * u ** 2.5 * .5
        s += np.sin(2 * np.pi * np.cumsum(200 + 1600 * u ** 2) / SR) * u ** 2 * .25
        return s
    def whoosh(L=.6):
        x = np.arange(int(L * SR)) / SR
        s = lowpass(highpass(rng.standard_normal(len(x)), 400), 3500) * np.sin(np.pi * x / L) ** 3
        l, r = s * np.linspace(1, .2, len(s)), s * np.linspace(.2, 1, len(s))
        return np.stack([l, r], 1)
    def blip(f=1400, L=.12):
        return osc(f, L, "sine") * env(L, .001, .03) + osc(f * 2, L, "sine") * env(L, .001, .015) * .3
    def glitch_sfx(L=.3):
        s = rng.standard_normal(int(L * SR))
        s = np.repeat(s[::40], 40)[:int(L * SR)] * (rng.random(int(L * SR) // 2000 + 1).repeat(2000)[:int(L * SR)] > .4)
        return s * .35
    def pad(ch, L, gain=1.0, cut=1800):
        s = sum(osc(hz(m), L, "saw", d) for m in ch for d in (-.004, .004))
        a = np.minimum(1, np.arange(len(s)) / (SR * .8)) * np.minimum(1, (len(s) - np.arange(len(s))) / (SR * .6))
        return lowpass(s * a, cut) * gain / len(ch)

    beat = 60 / 100
    CH = [[50, 53, 57, 62], [46, 50, 53, 58], [53, 57, 60, 65], [48, 52, 55, 60]]  # Dm Bb F C
    BASS = [38, 34, 41, 36]

    # --- A: intro (0 -> scene 2): drone + heartbeat, riser into the drop
    drop = START[1]
    add(mus, pad([38, 45, 50, 57], drop + .6, 1.0, 900), 0, .5)
    add(mus, boom(), 0.0, .9)
    hb = SP_START[0]
    while hb < drop - .8:
        add(mus, kick() * .8, hb, .6); add(mus, kick() * .5, hb + .22, .45); hb += 1.1
    add(sfx, riser(1.6), drop - 1.6, .45)

    def groove(a, b, full=True, cut=2400):
        tp, n_ = a, 0
        while tp < b - 1e-6:
            bar = (n_ // 4) % 4; pos = n_ % 4
            add(mus, kick(), tp, .9)
            if pos in (1, 3): add(mus, clap(), tp, .35 if full else .2)
            add(mus, hat(), tp + beat / 2, .28); add(mus, hat(), tp + beat / 4 * 3, .1)
            if full: add(mus, hat(), tp + beat / 4, .1)
            for e in range(2):
                add(mus, lowpass(osc(hz(BASS[bar]), beat / 2, "saw") * env(beat / 2, .004, .16), 700),
                    tp + e * beat / 2, .55)
            for s16 in range(4):
                m = CH[bar][(pos * 4 + s16) % 4] + 12
                add(mus, osc(hz(m), .25, "tri") * env(.25, .002, .07), tp + s16 * beat / 4, .1, pan=(-.4 if s16 % 2 else .4))
            if pos == 0: add(mus, pad(CH[bar], 4 * beat + .3, 1.0, cut), tp, .28)
            tp += beat; n_ += 1

    # --- B: groove through scenes 2..5
    groove(drop, START[5], full=True)
    # --- C: breakdown on the "job" warning — ticking clock + dark drone
    a5, b5 = START[5], START[6]
    add(mus, pad([38, 41, 45, 49], b5 - a5 + .5, 1.0, 700), a5, .6)
    tk = a5
    while tk < b5 - .2:
        add(mus, osc(2600, .025, "sine") * env(.025, .001, .006), tk, .22); tk += beat / 2
    add(sfx, riser(min(2.2, b5 - a5)), b5 - min(2.2, b5 - a5), .5)
    # --- D: epic finale
    groove(b5, START[7] + SPEECH[7] * .5, full=True, cut=3200)
    add(mus, pad([62, 65, 69, 74], START[7] + SPEECH[7] * .5 - b5, 1.0, 3500), b5, .18)
    fin = at(7, "تابعنا")
    add(mus, boom(4), fin, .8)
    add(mus, pad([50, 57, 62, 65, 69], DUR - fin + .2, 1.0, 2500), fin, .45)

    # --- SFX on cuts + text
    for b in range(1, N):
        add(sfx, whoosh(.6), START[b] - .3, .5)
        if TRANS[b] == "glitch": add(sfx, glitch_sfx(.35), START[b] - .15, .6)
    for s in SHAKES: add(sfx, boom(1.2), s, .38)
    for hs in HEAD:
        for h in hs:
            if h[5] in ("pop", "chip"): add(sfx, blip(1300 + random.randint(-2, 4) * 90), h[0], .22)
            if h[5] == "glitch": add(sfx, glitch_sfx(.3), h[0], .5)
    add(sfx, blip(1800, .2), fin + .6, .3); add(sfx, blip(2400, .2), fin + .7, .25)

    # --- voice-over
    for k, p in enumerate(PIECES):
        i = int(SP_START[k] * SR)
        vo[i:i + len(p)] += p[:max(0, n - i)]
    if HAVE_VO:
        rms = np.sqrt(np.mean(vo[vo != 0] ** 2)) + 1e-9
        vo *= .16 / rms
    # ducking from VO envelope
    e = np.abs(vo); win = int(.12 * SR)
    c = np.cumsum(np.concatenate([[0], e])); env_ = (c[win:] - c[:-win]) / win
    env_ = np.concatenate([env_, np.zeros(n - len(env_))])
    duck = 1 - .6 * np.clip(env_ / (np.max(env_) * .25 + 1e-9), 0, 1)
    k2 = int(.25 * SR); cc = np.cumsum(np.concatenate([[0], duck]))
    duck = np.concatenate([(cc[k2:] - cc[:-k2]) / k2, np.ones(k2 - 1) * duck[-1]])[:n]
    mus *= duck[:, None]
    # width on music
    mus[:, 1] = np.roll(mus[:, 1], 180)
    fade = np.clip(np.minimum(tt / .03, (DUR - tt) / 1.0), 0, 1)[:, None]
    mix = (mus * .42 + sfx * .55 + vo[:, None] * 1.0) * fade
    mix = np.tanh(mix * 1.2) / np.tanh(1.2)
    path = os.path.join(OUT, "mix.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())
    return path

# ================================================================ MAIN
def main():
    print(f"VO: {'real' if HAVE_VO else 'placeholder'}  speech={sum(SPEECH):.1f}s gap={GAP:.2f}s dur={DUR:.1f}s")
    print("scene starts:", " ".join(f"{s:.1f}" for s in START))
    if "--preview" in sys.argv:
        ts = [0.9, at(0, "بدأ") + .4, at(1, "وبيتكلم") + .5, at(2, "قبل") + .5, START[3] + .02, at(3, "سنين") + .8,
              at(4, "رأس") + .5, at(5, "الـ AI") + .6, at(5, "أحسن") + .5, START[6] + .03, at(6, "أداة") + .6,
              START[7] + .01, at(7, "شخص") + .5, DUR - 1.2]
        thumbs = [Image.fromarray(frame(int(t * FPS))).resize((270, 480)) for t in ts]
        sheet = Image.new("RGB", (270 * 7, 480 * 2))
        for j, th in enumerate(thumbs): sheet.paste(th, ((j % 7) * 270, (j // 7) * 480))
        sheet.save(os.path.join(OUT, "contact.png"))
        print("wrote out/contact.png"); return
    audio = synth_audio()
    out = os.path.join(OUT, "ai_ad.mp4")
    p = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", audio, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "9M", "-bufsize", "18M",
                          "-pix_fmt", "yuv420p", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k",
                          "-ar", "44100", "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    total = int(DUR * FPS)
    with Pool(os.cpu_count()) as pool:
        for i, fr in enumerate(pool.imap(frame, range(total), chunksize=4)):
            p.stdin.write(fr.tobytes())
            if i % 150 == 0: print(f"frame {i}/{total}", flush=True)
    p.stdin.close(); p.wait()
    print("wrote", out)

if __name__ == "__main__":
    main()
