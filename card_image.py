"""Renders the shareable GitHub stats card (PNG, 1200x630) in six color themes."""
import io
import os
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1200, 630
SCALE = 2  # draw at 2x, then downsample for smooth edges

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE_DIR, "assets", "fonts")

# Drop Inter-Regular.ttf and Inter-Bold.ttf into assets/fonts/ for the best look.
FONT_CANDIDATES = {
    False: [
        os.path.join(FONT_DIR, "Inter-Regular.ttf"),
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/opentype/inter/Inter-Regular.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    True: [
        os.path.join(FONT_DIR, "Inter-Bold.ttf"),
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
}

# ---------------------------------------------------------------------------
# Themes. Each one is a plain dict, so adding a seventh is just one more entry.
#   bg      three gradient stops (top-left -> bottom-right)
#   glows   two soft light spots: (r, g, b, strength)
#   ring    avatar ring gradient
#   tiles   accent colors of the four stat tiles
# ---------------------------------------------------------------------------
THEMES = {
    "aurora": dict(
        name="Aurora", emoji="🌌",
        bg=((11, 16, 32), (30, 27, 75), (76, 29, 149)),
        glows=((34, 211, 238, 80), (167, 139, 250, 70)),
        ring=((34, 211, 238), (167, 139, 250)),
        text=(241, 245, 249), soft=(203, 213, 225), muted=(148, 163, 184),
        accent=(34, 211, 238),
        tiles=((34, 211, 238), (251, 191, 36), (167, 139, 250), (244, 114, 182)),
        tile_fill=(255, 255, 255, 16), tile_line=(255, 255, 255, 34),
        divider=(255, 255, 255, 30), track=(58, 62, 105),
        avatar_bg=(49, 46, 129), avatar_fg=(241, 245, 249),
    ),
    "sunset": dict(
        name="Sunset", emoji="🌇",
        bg=((28, 10, 30), (112, 26, 66), (214, 96, 38)),
        glows=((251, 146, 60, 90), (244, 114, 182, 60)),
        ring=((251, 191, 36), (244, 63, 94)),
        text=(255, 247, 237), soft=(254, 215, 170), muted=(251, 190, 150),
        accent=(251, 191, 36),
        tiles=((251, 191, 36), (251, 113, 133), (251, 146, 60), (232, 121, 249)),
        tile_fill=(255, 255, 255, 18), tile_line=(255, 255, 255, 40),
        divider=(255, 255, 255, 36), track=(120, 50, 70),
        avatar_bg=(127, 29, 29), avatar_fg=(255, 247, 237),
    ),
    "forest": dict(
        name="Forest", emoji="🌲",
        bg=((5, 20, 15), (10, 55, 40), (22, 105, 62)),
        glows=((163, 230, 53, 55), (45, 212, 191, 60)),
        ring=((74, 222, 128), (163, 230, 53)),
        text=(240, 253, 244), soft=(187, 247, 208), muted=(134, 190, 160),
        accent=(74, 222, 128),
        tiles=((74, 222, 128), (250, 204, 21), (45, 212, 191), (163, 230, 53)),
        tile_fill=(255, 255, 255, 16), tile_line=(255, 255, 255, 34),
        divider=(255, 255, 255, 30), track=(30, 80, 60),
        avatar_bg=(20, 83, 45), avatar_fg=(240, 253, 244),
    ),
    "ocean": dict(
        name="Ocean", emoji="🌊",
        bg=((5, 16, 38), (8, 48, 92), (14, 116, 144)),
        glows=((56, 189, 248, 85), (45, 212, 191, 60)),
        ring=((56, 189, 248), (45, 212, 191)),
        text=(240, 249, 255), soft=(186, 230, 253), muted=(125, 170, 200),
        accent=(56, 189, 248),
        tiles=((56, 189, 248), (251, 191, 36), (129, 140, 248), (45, 212, 191)),
        tile_fill=(255, 255, 255, 16), tile_line=(255, 255, 255, 34),
        divider=(255, 255, 255, 30), track=(28, 70, 110),
        avatar_bg=(12, 74, 110), avatar_fg=(240, 249, 255),
    ),
    "sakura": dict(
        name="Sakura", emoji="🌸",
        bg=((30, 10, 38), (92, 30, 104), (196, 84, 146)),
        glows=((244, 114, 182, 85), (192, 132, 252, 60)),
        ring=((249, 168, 212), (192, 132, 252)),
        text=(253, 242, 248), soft=(251, 207, 232), muted=(224, 170, 205),
        accent=(249, 168, 212),
        tiles=((249, 168, 212), (253, 224, 71), (192, 132, 252), (251, 113, 133)),
        tile_fill=(255, 255, 255, 18), tile_line=(255, 255, 255, 40),
        divider=(255, 255, 255, 34), track=(110, 50, 120),
        avatar_bg=(112, 26, 117), avatar_fg=(253, 242, 248),
    ),
    "daylight": dict(
        name="Daylight", emoji="☀️",
        bg=((250, 250, 255), (232, 236, 255), (203, 213, 255)),
        glows=((129, 140, 248, 70), (244, 114, 182, 40)),
        ring=((99, 102, 241), (236, 72, 153)),
        text=(15, 23, 42), soft=(51, 65, 85), muted=(100, 116, 139),
        accent=(79, 70, 229),
        tiles=((79, 70, 229), (217, 119, 6), (124, 58, 237), (219, 39, 119)),
        tile_fill=(255, 255, 255, 170), tile_line=(15, 23, 42, 26),
        divider=(15, 23, 42, 28), track=(203, 213, 225),
        avatar_bg=(199, 210, 254), avatar_fg=(49, 46, 129),
    ),
}
THEME_ORDER = ["aurora", "sunset", "forest", "ocean", "sakura", "daylight"]
DEFAULT_THEME = "aurora"

ALIASES = {
    "dark": "aurora", "purple": "aurora", "violet": "aurora",
    "orange": "sunset", "red": "sunset", "warm": "sunset",
    "green": "forest", "blue": "ocean", "teal": "ocean",
    "pink": "sakura", "light": "daylight", "white": "daylight", "day": "daylight",
}


def resolve_theme(name):
    """'Ocean', 'blue', 'light' ... -> theme id, or None if unknown."""
    n = (name or "").strip().lower()
    n = ALIASES.get(n, n)
    return n if n in THEMES else None


LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "Java": "#b07219", "C": "#8a8a8a", "C++": "#f34b7d", "C#": "#2ea043",
    "Go": "#00ADD8", "Rust": "#dea584", "PHP": "#8892be", "Ruby": "#cc342d",
    "Swift": "#F05138", "Kotlin": "#A97BFF", "Dart": "#00B4AB",
    "HTML": "#e34c26", "CSS": "#7c5cbf", "SCSS": "#c6538c", "Shell": "#89e051",
    "Jupyter Notebook": "#DA5B0B", "Vue": "#41b883", "Lua": "#5b6fe0",
    "Dockerfile": "#384d54", "Makefile": "#6a9f3f", "Scala": "#dc322f",
    "R": "#198CE7", "Objective-C": "#438eff", "Haskell": "#5e5086",
}
FALLBACK_COLORS = ["#22d3ee", "#a78bfa", "#f472b6", "#fbbf24", "#34d399", "#fb923c"]
OTHER_COLOR = "#64748b"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _hex(c: str):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


@lru_cache(maxsize=32)
def _font(size: int, bold: bool = False):
    px = int(size * SCALE)
    for path in FONT_CANDIDATES[bold]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, px)
            except OSError:
                continue
    return ImageFont.load_default(px)


def _num(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.1f}k".replace(".0k", "k")
    return str(n)


def _clean(text) -> str:
    """Keep Latin text only. The font can't draw emoji or non-Latin scripts."""
    if not text:
        return ""
    keep = "–—‘’“”…•"
    out = "".join(ch for ch in str(text) if (ord(ch) < 0x250 and ch.isprintable()) or ch in keep)
    return " ".join(out.split())


def _fit(draw, text, font, max_w):
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def _wrap(draw, text, font, max_w, max_lines):
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,;: ") + "…"
    return [_fit(draw, ln, font, max_w) for ln in lines]


def _background(w, h, t):
    sw, sh = 96, 50
    small = Image.new("RGB", (sw, sh))
    px = small.load()
    c1, c2, c3 = t["bg"]
    for y in range(sh):
        for x in range(sw):
            g = (x / sw + y / sh) / 2
            if g < 0.55:
                k, a, b = g / 0.55, c1, c2
            else:
                k, a, b = (g - 0.55) / 0.45, c2, c3
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))
    bg = small.resize((w, h), Image.BICUBIC)

    def glow(spec, box):
        m = Image.new("L", (max(w // 8, 1), max(h // 8, 1)), 0)
        ImageDraw.Draw(m).ellipse([int(v / 8) for v in box], fill=spec[3])
        m = m.filter(ImageFilter.GaussianBlur(14)).resize((w, h), Image.BICUBIC)
        bg.paste(Image.new("RGB", (w, h), spec[:3]), (0, 0), m)

    glow(t["glows"][0], (w * 0.55, -h * 0.35, w * 1.05, h * 0.45))
    glow(t["glows"][1], (-w * 0.1, h * 0.7, w * 0.35, h * 1.3))
    return bg.convert("RGBA")


def _avatar(img, avatar_bytes, login, x, y, size, t):
    ring = int(5 * SCALE)
    n = size + 2 * ring
    a, b = t["ring"]
    grad = Image.new("RGB", (n, n))
    gp = grad.load()
    for j in range(n):
        for i in range(n):
            k = (i + j) / (2 * n)
            gp[i, j] = tuple(int(a[c] + (b[c] - a[c]) * k) for c in range(3))
    ring_mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(ring_mask).ellipse([0, 0, n - 1, n - 1], fill=255)
    img.paste(grad, (x - ring, y - ring), ring_mask)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    photo = None
    if avatar_bytes:
        try:
            photo = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((size, size), Image.LANCZOS)
        except Exception:
            photo = None
    if photo is None:
        photo = Image.new("RGBA", (size, size), t["avatar_bg"] + (255,))
        d = ImageDraw.Draw(photo)
        f = _font(64, True)
        ch = (login[:1] or "?").upper()
        d.text(((size - d.textlength(ch, font=f)) / 2, size * 0.2), ch, font=f, fill=t["avatar_fg"])
    img.paste(photo, (x, y), mask)


def _pill_bar(img, x, y, w, h, colors, weights, track):
    """Rounded multi-color bar. weights=None draws an empty track."""
    bar = Image.new("RGBA", (w, h), track + (255,))
    if weights:
        bd = ImageDraw.Draw(bar)
        total, cx = sum(weights), 0
        for i, wt in enumerate(weights):
            seg = w - cx if i == len(weights) - 1 else int(w * wt / total)
            bd.rectangle([cx, 0, cx + seg, h], fill=colors[i])
            cx += seg
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=255)
    img.paste(bar, (x, y), mask)


# ---------------------------------------------------------------------------
# the card
# ---------------------------------------------------------------------------

def render_card(data: dict, avatar_bytes=None, theme: str = DEFAULT_THEME) -> bytes:
    """data: login, name, bio, repos, stars, forks, followers, since,
    languages [(name, count)], top_repo (name, stars) | None"""
    t = THEMES.get(theme) or THEMES[DEFAULT_THEME]
    S = SCALE
    w, h = W * S, H * S
    img = _background(w, h, t)

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    pad, gap, tile_w, tile_h, tile_y = 56, 20, 257, 128, 250
    for i in range(4):
        x0 = (pad + i * (tile_w + gap)) * S
        od.rounded_rectangle(
            [x0, tile_y * S, x0 + tile_w * S, (tile_y + tile_h) * S],
            radius=20 * S, fill=t["tile_fill"], outline=t["tile_line"], width=S,
        )
    od.line([(pad * S, 552 * S), ((W - pad) * S, 552 * S)], fill=t["divider"], width=S)
    img = Image.alpha_composite(img, overlay)

    _avatar(img, avatar_bytes, data["login"], pad * S, pad * S, 150 * S, t)
    d = ImageDraw.Draw(img)

    tx, max_w = 240 * S, (W - 240 - pad) * S
    name = _clean(data.get("name")) or data["login"]
    d.text((tx, 62 * S), _fit(d, name, _font(46, True), max_w), font=_font(46, True), fill=t["text"])
    d.text((tx, 120 * S), f"@{data['login']}", font=_font(26), fill=t["accent"])
    bio = _clean(data.get("bio"))
    if bio:
        for i, line in enumerate(_wrap(d, bio, _font(24), max_w, 2)):
            d.text((tx, (166 + i * 34) * S), line, font=_font(24), fill=t["soft"])

    tiles = [
        ("Repositories", data["repos"]), ("Stars earned", data["stars"]),
        ("Followers", data["followers"]), ("Forks", data["forks"]),
    ]
    for i, (label, value) in enumerate(tiles):
        x0 = (pad + i * (tile_w + gap)) * S
        d.rounded_rectangle(
            [x0 + 22 * S, (tile_y + 26) * S, x0 + 26 * S, (tile_y + 102) * S],
            radius=2 * S, fill=t["tiles"][i],
        )
        d.text((x0 + 44 * S, (tile_y + 20) * S), _num(value), font=_font(48, True), fill=t["text"])
        d.text((x0 + 44 * S, (tile_y + 82) * S), label, font=_font(22), fill=t["muted"])

    d.text((pad * S, 410 * S), "TOP LANGUAGES", font=_font(20, True), fill=t["muted"])
    note, nf = "by repository count", _font(20)
    d.text(((W - pad) * S - d.textlength(note, font=nf), 410 * S), note, font=nf, fill=t["muted"])

    langs = list(data.get("languages") or [])
    bx, by, bw, bh = pad * S, 446 * S, (W - 2 * pad) * S, 16 * S
    if langs:
        total = sum(c for _, c in langs)
        items = list(langs[:5])
        rest = total - sum(c for _, c in items)
        if rest > 0:
            items.append(("Other", rest))

        colors, fi = [], 0
        for n, _ in items:
            if n == "Other":
                colors.append(_hex(OTHER_COLOR))
            elif n in LANG_COLORS:
                colors.append(_hex(LANG_COLORS[n]))
            else:
                colors.append(_hex(FALLBACK_COLORS[fi % len(FALLBACK_COLORS)]))
                fi += 1

        _pill_bar(img, bx, by, bw, bh, colors, [c for _, c in items], t["track"])
        d = ImageDraw.Draw(img)

        lx, ly, lf = pad * S, 486 * S, _font(22)
        for idx, (n, c) in enumerate(items):
            pct = c / total * 100
            label = f"{n}  {pct:.0f}%" if pct >= 1 else f"{n}  <1%"
            item_w = 24 * S + d.textlength(label, font=lf)
            if lx + item_w > (W - pad) * S:
                break
            d.ellipse([lx, ly + 7 * S, lx + 14 * S, ly + 21 * S], fill=colors[idx])
            d.text((lx + 24 * S, ly), label, font=lf, fill=t["soft"])
            lx += item_w + 30 * S
    else:
        _pill_bar(img, bx, by, bw, bh, [], None, t["track"])
        d = ImageDraw.Draw(img)
        d.text((pad * S, 486 * S), "No language data yet", font=_font(22), fill=t["muted"])

    ff = _font(22)
    if data.get("top_repo"):
        rn, rs = data["top_repo"]
        text = _fit(d, f"Top repo  {_clean(rn)}  ·  {_num(rs)} stars", ff, 640 * S)
        d.text((pad * S, 574 * S), text, font=ff, fill=t["muted"])
    brand = f"Member since {data['since']}  ·  DevHub Assistant"
    d.text(((W - pad) * S - d.textlength(brand, font=ff), 574 * S), brand, font=ff, fill=t["muted"])

    out = img.convert("RGB").resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# the theme picker image (3 x 2 grid of swatches)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def render_theme_preview() -> bytes:
    S = SCALE
    w, h = W * S, H * S
    canvas = Image.new("RGBA", (w, h), (14, 16, 26, 255))
    pad, gap = 36, 28
    sw = (W - 2 * pad - 2 * gap) // 3
    sh = (H - 2 * pad - gap) // 2

    spots = []
    for i, tid in enumerate(THEME_ORDER):
        t = THEMES[tid]
        x = (pad + (i % 3) * (sw + gap)) * S
        y = (pad + (i // 3) * (sh + gap)) * S
        sw_img = _background(sw * S, sh * S, t)
        m = Image.new("L", (sw * S, sh * S), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, sw * S - 1, sh * S - 1], radius=24 * S, fill=255)
        canvas.paste(sw_img, (x, y), m)
        spots.append((tid, t, x, y))

    # translucent mini tiles, same look as the real card
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    inner = sw - 52
    tw = (inner - 3 * 10) // 4
    for _, t, x, y in spots:
        for k in range(4):
            tx0 = x + (26 + k * (tw + 10)) * S
            od.rounded_rectangle(
                [tx0, y + 96 * S, tx0 + tw * S, y + 156 * S],
                radius=12 * S, fill=t["tile_fill"], outline=t["tile_line"], width=S,
            )
    canvas = Image.alpha_composite(canvas, overlay)
    d = ImageDraw.Draw(canvas)

    sample_colors = [_hex(LANG_COLORS[n]) for n in ("Python", "TypeScript", "Go", "Shell", "Rust")]
    for _, t, x, y in spots:
        d.text((x + 26 * S, y + 24 * S), t["name"], font=_font(36, True), fill=t["text"])
        d.text((x + 26 * S, y + 66 * S), "@username", font=_font(20), fill=t["accent"])
        for k in range(4):
            tx0 = x + (26 + k * (tw + 10)) * S
            d.rounded_rectangle(
                [tx0 + 8 * S, y + 108 * S, tx0 + 11 * S, y + 144 * S], radius=S, fill=t["tiles"][k]
            )
            d.rounded_rectangle(
                [tx0 + 20 * S, y + 112 * S, tx0 + (tw - 10) * S, y + 124 * S],
                radius=6 * S, fill=t["muted"],
            )
        _pill_bar(canvas, x + 26 * S, y + 186 * S, inner * S, 12 * S,
                  sample_colors, [41, 24, 16, 8, 5], t["track"])
        d = ImageDraw.Draw(canvas)

    out = canvas.convert("RGB").resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()