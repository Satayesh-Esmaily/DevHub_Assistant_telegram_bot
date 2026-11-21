"""Renders the shareable GitHub stats card as a PNG (1200x630)."""
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

BG1, BG2, BG3 = (11, 16, 32), (30, 27, 75), (76, 29, 149)
CYAN, VIOLET = (34, 211, 238), (167, 139, 250)
PINK, AMBER = (244, 114, 182), (251, 191, 36)
TEXT, SOFT, MUTED = (241, 245, 249), (203, 213, 225), (148, 163, 184)

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


def _background(w, h):
    sw, sh = 96, 50
    small = Image.new("RGB", (sw, sh))
    px = small.load()
    for y in range(sh):
        for x in range(sw):
            t = (x / sw + y / sh) / 2
            if t < 0.55:
                k, a, b = t / 0.55, BG1, BG2
            else:
                k, a, b = (t - 0.55) / 0.45, BG2, BG3
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))
    bg = small.resize((w, h), Image.BICUBIC)

    def glow(color, box, alpha):
        m = Image.new("L", (w // 8, h // 8), 0)
        ImageDraw.Draw(m).ellipse([int(v / 8) for v in box], fill=alpha)
        m = m.filter(ImageFilter.GaussianBlur(14)).resize((w, h), Image.BICUBIC)
        bg.paste(Image.new("RGB", (w, h), color), (0, 0), m)

    glow(CYAN, (w * 0.55, -h * 0.35, w * 1.05, h * 0.45), 80)
    glow(VIOLET, (-w * 0.1, h * 0.7, w * 0.35, h * 1.3), 70)
    return bg.convert("RGBA")


def _avatar(img, avatar_bytes, login, x, y, size):
    ring = int(5 * SCALE)
    # gradient ring
    grad = Image.new("RGB", (size + 2 * ring, size + 2 * ring))
    gp = grad.load()
    n = size + 2 * ring
    for j in range(n):
        for i in range(n):
            t = (i + j) / (2 * n)
            gp[i, j] = tuple(int(CYAN[c] + (VIOLET[c] - CYAN[c]) * t) for c in range(3))
    ring_mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(ring_mask).ellipse([0, 0, n - 1, n - 1], fill=255)
    img.paste(grad, (x - ring, y - ring), ring_mask)

    # inner dark gap + photo
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    photo = None
    if avatar_bytes:
        try:
            photo = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((size, size), Image.LANCZOS)
        except Exception:
            photo = None
    if photo is None:
        photo = Image.new("RGBA", (size, size), (49, 46, 129, 255))
        d = ImageDraw.Draw(photo)
        f = _font(64, True)
        ch = (login[:1] or "?").upper()
        tw = d.textlength(ch, font=f)
        d.text(((size - tw) / 2, size * 0.2), ch, font=f, fill=TEXT)
    img.paste(photo, (x, y), mask)


def render_card(data: dict, avatar_bytes=None) -> bytes:
    """data: login, name, bio, repos, stars, forks, followers, since,
    languages [(name, count)], top_repo (name, stars) | None"""
    S = SCALE
    w, h = W * S, H * S
    img = _background(w, h)

    # translucent layer: stat tiles, footer line
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    pad, gap, tile_w, tile_h, tile_y = 56, 20, 257, 128, 250
    for i in range(4):
        x0 = (pad + i * (tile_w + gap)) * S
        od.rounded_rectangle(
            [x0, tile_y * S, x0 + tile_w * S, (tile_y + tile_h) * S],
            radius=20 * S, fill=(255, 255, 255, 16), outline=(255, 255, 255, 34), width=S,
        )
    od.line([(pad * S, 552 * S), ((W - pad) * S, 552 * S)], fill=(255, 255, 255, 30), width=S)
    img = Image.alpha_composite(img, overlay)

    _avatar(img, avatar_bytes, data["login"], pad * S, pad * S, 150 * S)
    d = ImageDraw.Draw(img)

    # header text
    tx, max_w = 240 * S, (W - 240 - pad) * S
    name = _clean(data.get("name")) or data["login"]
    d.text((tx, 62 * S), _fit(d, name, _font(46, True), max_w), font=_font(46, True), fill=TEXT)
    d.text((tx, 120 * S), f"@{data['login']}", font=_font(26), fill=CYAN)
    bio = _clean(data.get("bio"))
    if bio:
        for i, line in enumerate(_wrap(d, bio, _font(24), max_w, 2)):
            d.text((tx, (166 + i * 34) * S), line, font=_font(24), fill=SOFT)

    # stat tiles
    tiles = [
        ("Repositories", data["repos"], CYAN),
        ("Stars earned", data["stars"], AMBER),
        ("Followers", data["followers"], VIOLET),
        ("Forks", data["forks"], PINK),
    ]
    for i, (label, value, color) in enumerate(tiles):
        x0 = (pad + i * (tile_w + gap)) * S
        d.rounded_rectangle(
            [x0 + 22 * S, (tile_y + 26) * S, x0 + 26 * S, (tile_y + 102) * S],
            radius=2 * S, fill=color,
        )
        d.text((x0 + 44 * S, (tile_y + 20) * S), _num(value), font=_font(48, True), fill=TEXT)
        d.text((x0 + 44 * S, (tile_y + 82) * S), label, font=_font(22), fill=MUTED)

    # languages
    d.text((pad * S, 410 * S), "TOP LANGUAGES", font=_font(20, True), fill=MUTED)
    note = "by repository count"
    nf = _font(20)
    d.text(((W - pad) * S - d.textlength(note, font=nf), 410 * S), note, font=nf, fill=MUTED)

    langs = list(data.get("languages") or [])
    bx, by, bw, bh = pad * S, 446 * S, (W - 2 * pad) * S, 16 * S
    if langs:
        total = sum(c for _, c in langs)
        top = langs[:5]
        rest = total - sum(c for _, c in top)
        items = [(n, c) for n, c in top]
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

        bar = Image.new("RGBA", (bw, bh), (58, 62, 105, 255))
        bd = ImageDraw.Draw(bar)
        cx = 0
        for idx, (n, c) in enumerate(items):
            seg = bw - cx if idx == len(items) - 1 else int(bw * c / total)
            bd.rectangle([cx, 0, cx + seg, bh], fill=colors[idx])
            cx += seg
        bmask = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(bmask).rounded_rectangle([0, 0, bw - 1, bh - 1], radius=bh // 2, fill=255)
        img.paste(bar, (bx, by), bmask)
        d = ImageDraw.Draw(img)

        lx, ly, lf = pad * S, 486 * S, _font(22)
        for idx, (n, c) in enumerate(items):
            pct = c / total * 100
            label = f"{n}  {pct:.0f}%" if pct >= 1 else f"{n}  <1%"
            item_w = 24 * S + d.textlength(label, font=lf)
            if lx + item_w > (W - pad) * S:
                break
            d.ellipse([lx, ly + 7 * S, lx + 14 * S, ly + 21 * S], fill=colors[idx])
            d.text((lx + 24 * S, ly), label, font=lf, fill=SOFT)
            lx += item_w + 30 * S
    else:
        bar = Image.new("RGBA", (bw, bh), (58, 62, 105, 255))
        bmask = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(bmask).rounded_rectangle([0, 0, bw - 1, bh - 1], radius=bh // 2, fill=255)
        img.paste(bar, (bx, by), bmask)
        d = ImageDraw.Draw(img)
        d.text((pad * S, 486 * S), "No language data yet", font=_font(22), fill=MUTED)

    # footer
    ff = _font(22)
    if data.get("top_repo"):
        rn, rs = data["top_repo"]
        text = _fit(d, f"Top repo  {_clean(rn)}  ·  {_num(rs)} stars", ff, 640 * S)
        d.text((pad * S, 574 * S), text, font=ff, fill=MUTED)
    brand = f"Member since {data['since']}  ·  DevHub Assistant"
    d.text(((W - pad) * S - d.textlength(brand, font=ff), 574 * S), brand, font=ff, fill=MUTED)

    out = img.convert("RGB").resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()