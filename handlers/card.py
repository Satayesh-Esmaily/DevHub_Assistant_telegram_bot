import asyncio
import re
import time
from collections import Counter

import httpx
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

import github_api as gh
import storage
from card_image import render_card

USER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
CACHE_TTL = 600   # reuse a finished card for 10 minutes
COOLDOWN = 8      # seconds between /card requests per user
_cache: dict = {}


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


async def card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    token = storage.get_token(uid)

    args = [a for a in context.args if a.lower() != "file"]
    as_file = len(args) != len(context.args)

    if args:
        login = args[0].lstrip("@")
    elif token:
        login = storage.get_login(uid)
    else:
        await update.message.reply_text(
            "Usage: /card <username>\n"
            "Add 'file' to get the full quality PNG: /card <username> file\n"
            "Tip: after /login, just send /card for your own card."
        )
        return

    if not USER_RE.match(login):
        await update.message.reply_text("That doesn't look like a valid GitHub username.")
        return

    now = time.time()
    if now - context.user_data.get("last_card", 0) < COOLDOWN:
        await update.message.reply_text("⏳ Easy there, wait a few seconds and try again.")
        return
    context.user_data["last_card"] = now

    await update.effective_chat.send_action(ChatAction.UPLOAD_PHOTO)

    hit = _cache.get(login.lower())
    if hit and now - hit[0] < CACHE_TTL:
        png = hit[1]
    else:
        data, err = await _collect(login, token)
        if err == "not_found":
            await update.message.reply_text("User not found.")
            return
        if err:
            await update.message.reply_text(
                "GitHub didn't answer (probably the rate limit). Try again later, "
                "or /login to get a much higher limit."
            )
            return
        avatar = await _avatar(data["avatar_url"])
        png = await asyncio.to_thread(render_card, data, avatar)  # CPU work off the event loop
        if len(_cache) > 200:
            _cache.clear()
        _cache[login.lower()] = (now, png)

    caption = f"📊 {login} on GitHub\nhttps://github.com/{login}"
    if as_file:
        await update.message.reply_document(
            document=png, filename=f"{login}-github-card.png", caption=caption
        )
    else:
        await update.message.reply_photo(photo=png, caption=caption)