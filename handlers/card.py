import asyncio
import re
import time
from collections import Counter

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import github_api as gh
import storage
from card_image import (
    THEME_ORDER, THEMES, render_card, render_theme_preview, resolve_theme,
)

USER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
CACHE_TTL = 600       # reuse fetched GitHub data and finished cards for 10 minutes
COOLDOWN = 8          # seconds between /card commands per user
CLICK_COOLDOWN = 2    # seconds between theme button presses per user

_data_cache: dict = {}   # login -> (time, data, avatar_bytes)
_png_cache: dict = {}    # (login, theme) -> (time, png)

THEME_LIST = ", ".join(THEMES[t]["name"] for t in THEME_ORDER)
USAGE = (
    "Usage:\n"
    "/card <username>  → pick a theme, then I draw the card\n"
    "/card <username> <theme>  → skip the picker, e.g. /card torvalds ocean\n"
    "/card me <theme>  → your own card (after /login)\n"
    "Add 'file' for the full quality PNG: /card torvalds ocean file\n\n"
    f"Themes: {THEME_LIST}"
)


# ---------- data ----------

async def _avatar(url: str):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params={"s": 300})
        return r.content if r.status_code == 200 else None
    except Exception:
        return None


async def _collect(login: str, token):
    """Returns (data, error). error is 'not_found', 'limit' or None."""
    ur, rr = await asyncio.gather(
        gh.get(f"/users/{login}", token),
        gh.get(
            f"/users/{login}/repos",
            token,
            {"per_page": 100, "type": "owner", "sort": "pushed"},
        ),
    )
    if ur.status_code == 404:
        return None, "not_found"
    if ur.status_code != 200 or rr.status_code != 200:
        return None, "limit"

    u = ur.json()
    repos = [x for x in rr.json() if not x["fork"]]
    langs = Counter(x["language"] for x in repos if x.get("language"))
    top = max(repos, key=lambda x: x["stargazers_count"], default=None)

    data = {
        "login": u["login"],
        "name": u.get("name"),
        "bio": u.get("bio"),
        "repos": u["public_repos"],
        "stars": sum(x["stargazers_count"] for x in repos),
        "forks": sum(x["forks_count"] for x in repos),
        "followers": u["followers"],
        "since": u["created_at"][:4],
        "languages": langs.most_common(),
        "top_repo": (top["name"], top["stargazers_count"]) if top else None,
        "avatar_url": u["avatar_url"],
    }
    return data, None


async def _get_data(login: str, token):
    key = login.lower()
    hit = _data_cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1], hit[2], None
    data, err = await _collect(login, token)
    if err:
        return None, None, err
    avatar = await _avatar(data["avatar_url"])
    if len(_data_cache) > 100:
        _data_cache.clear()
    _data_cache[key] = (time.time(), data, avatar)
    return data, avatar, None


async def _make_png(login: str, theme: str, token):
    """Returns (png_bytes, error)."""
    key = (login.lower(), theme)
    hit = _png_cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1], None
    data, avatar, err = await _get_data(login, token)
    if err:
        return None, err
    png = await asyncio.to_thread(render_card, data, avatar, theme)  # CPU work off the event loop
    if len(_png_cache) > 60:
        _png_cache.clear()
    _png_cache[key] = (time.time(), png)
    return png, None


def _err_text(err: str) -> str:
    if err == "not_found":
        return "User not found."
    return (
        "GitHub didn't answer (probably the rate limit). Try again later, "
        "or /login to get a much higher limit."
    )


# ---------- UI helpers ----------

def _parse_args(args):
    """-> (login or None, theme id or None, unknown theme text or None, as_file)"""
    tokens = [a for a in args if a.lower() != "file"]
    as_file = len(tokens) != len(args)
    login = tokens[0].lstrip("@") if tokens else None
    theme = bad = None
    if len(tokens) > 1:
        theme = resolve_theme(tokens[1])
        if theme is None:
            bad = tokens[1]
    return login, theme, bad, as_file


def _theme_kb(login: str, mode: str, current=None):
    """mode: 'p' = photo, 'f' = file. callback_data stays well under Telegram's 64 byte limit."""
    buttons = []
    for tid in THEME_ORDER:
        label = f"{THEMES[tid]['emoji']} {THEMES[tid]['name']}"
        if tid == current:
            label = "✓ " + label
        buttons.append(InlineKeyboardButton(label, callback_data=f"cp:{tid}:{mode}:{login}"))
    return InlineKeyboardMarkup([buttons[:3], buttons[3:]])


def _caption(login: str, theme: str) -> str:
    return f"📊 {login} · {THEMES[theme]['name']} theme\nhttps://github.com/{login}"


# ---------- /card ----------

async def card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    token = storage.get_token(uid)
    login, theme, bad_theme, as_file = _parse_args(context.args)

    if bad_theme:
        await update.message.reply_text(f"I don't know the theme '{bad_theme}'.\nThemes: {THEME_LIST}")
        return

    if login is None or login.lower() == "me":
        if not token:
            await update.message.reply_text(USAGE if login is None else "Please /login first.")
            return
        login = storage.get_login(uid)

    if not USER_RE.match(login):
        await update.message.reply_text("That doesn't look like a valid GitHub username.")
        return

    now = time.time()
    if now - context.user_data.get("last_card", 0) < COOLDOWN:
        await update.message.reply_text("⏳ Easy there, wait a few seconds and try again.")
        return
    context.user_data["last_card"] = now

    mode = "f" if as_file else "p"

    # No theme given: show the picker (a preview of all six themes + buttons)
    if theme is None:
        preview = context.bot_data.get("theme_preview_id")
        if not preview:
            preview = await asyncio.to_thread(render_theme_preview)
        sent = await update.message.reply_photo(
            photo=preview,
            caption=f"🎨 Choose a theme for {login}'s card:",
            reply_markup=_theme_kb(login, mode),
        )
        if sent.photo:
            context.bot_data["theme_preview_id"] = sent.photo[-1].file_id  # reuse, don't re-upload
        return

    # Theme given: draw straight away
    await update.effective_chat.send_action(ChatAction.UPLOAD_PHOTO)
    png, err = await _make_png(login, theme, token)
    if err:
        await update.message.reply_text(_err_text(err))
        return
    if as_file:
        await update.message.reply_document(
            document=png, filename=f"{login}-github-card.png", caption=_caption(login, theme)
        )
    else:
        await update.message.reply_photo(
            photo=png, caption=_caption(login, theme), reply_markup=_theme_kb(login, mode, theme)
        )


# ---------- theme button pressed ----------

async def theme_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        _, theme, mode, login = q.data.split(":", 3)
    except ValueError:
        await q.answer()
        return
    if theme not in THEMES or not USER_RE.match(login):
        await q.answer()
        return

    # in groups only the person who asked may choose
    origin = q.message.reply_to_message
    if origin and origin.from_user and origin.from_user.id != q.from_user.id:
        await q.answer("Only the person who asked can pick a theme.", show_alert=True)
        return

    now = time.time()
    if now - context.user_data.get("last_click", 0) < CLICK_COOLDOWN:
        await q.answer("One moment…")
        return
    context.user_data["last_click"] = now

    await q.answer(f"🎨 Drawing the {THEMES[theme]['name']} card…")
    png, err = await _make_png(login, theme, storage.get_token(q.from_user.id))
    if err:
        await q.message.reply_text(_err_text(err))
        return

    if mode == "f":
        await q.message.reply_document(
            document=png, filename=f"{login}-{theme}-github-card.png", caption=_caption(login, theme)
        )
        return

    try:  # turn the picker into the card; the buttons stay so they can try another theme
        await q.edit_message_media(
            media=InputMediaPhoto(media=png, caption=_caption(login, theme)),
            reply_markup=_theme_kb(login, mode, theme),
        )
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise