import asyncio
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import github_api as gh
import storage
from config import PUBLIC_URL, WEBHOOK_SECRET
from handlers.basic import esc
from webhook_server import HOOK_EVENTS


def _valid_repo(args):
    return args and "/" in args[0] and len(args[0].split("/")) == 2


# ---------- WATCH / UNWATCH ----------

async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = storage.get_token(update.effective_user.id)
    if not token:
        await update.message.reply_text("Please /login first.")
        return
    if not _valid_repo(context.args):
        await update.message.reply_text("Usage: /watch <owner/name>")
        return

    repo = context.args[0]
    chat_id = update.effective_chat.id
    if storage.get_watch(chat_id, repo):
        await update.message.reply_text("Already watching this repo in this chat.")
        return

    r = await gh.post(
        f"/repos/{repo}/hooks",
        token,
        {
            "name": "web",
            "active": True,
            "events": HOOK_EVENTS,
            "config": {
                "url": f"{PUBLIC_URL}/webhook/{chat_id}",
                "content_type": "json",
                "secret": WEBHOOK_SECRET,
            },
        },
    )
    if r.status_code == 201:
        storage.add_watch(chat_id, repo, r.json()["id"])
        await update.message.reply_text(
            f"👀 Now watching <b>{esc(repo)}</b>.\n"
            f"You'll get commits, issues, PRs, stars, forks, releases and CI results here.",
            parse_mode=ParseMode.HTML,
        )
    elif r.status_code in (403, 404):
        await update.message.reply_text(
            "❌ I couldn't create the webhook. You need admin access to the repo, "
            "and your login must include hook permission (try /logout then /login)."
        )
    elif r.status_code == 422:
        await update.message.reply_text("❌ GitHub rejected the webhook (maybe it already exists or the URL is invalid).")
    else:
        await update.message.reply_text(f"❌ Failed (HTTP {r.status_code}).")


async def unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = storage.get_token(update.effective_user.id)
    if not token:
        await update.message.reply_text("Please /login first.")
        return
    if not _valid_repo(context.args):
        await update.message.reply_text("Usage: /unwatch <owner/name>")
        return

    repo = context.args[0]
    chat_id = update.effective_chat.id
    hook_id = storage.get_watch(chat_id, repo)
    if not hook_id:
        await update.message.reply_text("I'm not watching that repo in this chat.")
        return

    await gh.delete(f"/repos/{repo}/hooks/{hook_id}", token)
    storage.remove_watch(chat_id, repo)
    await update.message.reply_text(f"🛑 Stopped watching {repo}.")


async def watching(update: Update, context: ContextTypes.DEFAULT_TYPE):
    repos = storage.list_watches(update.effective_chat.id)
    if not repos:
        await update.message.reply_text("Not watching anything here. Use /watch <owner/name>.")
        return
    lines = ["👀 <b>Watching in this chat</b>\n"] + [f"• {esc(r)}" for r in repos]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ---------- DIGEST ----------

async def build_digest(token: str, login: str) -> str:
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = await gh.get(
        "/user/repos",
        token,
        {"sort": "pushed", "per_page": 10, "affiliation": "owner"},
    )
    if r.status_code != 200:
        return "Could not load your repos. Try /logout and /login again."
    repos = r.json()

    async def commits_count(full_name):
        cr = await gh.get(
            f"/repos/{full_name}/commits", token, {"since": since, "per_page": 100}
        )
        return len(cr.json()) if cr.status_code == 200 and isinstance(cr.json(), list) else 0

    counts = await asyncio.gather(*(commits_count(x["full_name"]) for x in repos))

    lines = [f"📰 <b>Daily digest for {esc(login)}</b>\n<i>last 24 hours</i>\n"]
    active = 0
    for repo_data, n in zip(repos, counts):
        if n == 0:
            continue
        active += 1
        lines.append(
            f"• <a href=\"{repo_data['html_url']}\">{esc(repo_data['name'])}</a>: "
            f"{n} commit(s) · ⭐ {repo_data['stargazers_count']} · 🐞 {repo_data['open_issues_count']}"
        )
    if active == 0:
        lines.append("No commits in your recent repos. A perfect day to push something 😉")
    return "\n".join(lines)


async def digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    token = storage.get_token(uid)
    if not token:
        await update.message.reply_text("Please /login first.")
        return

    arg = context.args[0].lower() if context.args else ""
    if arg == "on":
        storage.set_digest(uid, True)
        await update.message.reply_text("✅ Daily digest enabled. Use /digest off to stop.")
    elif arg == "off":
        storage.set_digest(uid, False)
        await update.message.reply_text("Daily digest disabled.")
    else:
        text = await build_digest(token, storage.get_login(uid))
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )
        if not storage.is_digest_on(uid):
            await update.message.reply_text("Tip: /digest on to get this every day.")


async def send_daily_digests(context: ContextTypes.DEFAULT_TYPE):
    for uid in storage.list_digest_subs():
        token = storage.get_token(uid)
        if not token:
            storage.set_digest(uid, False)
            continue
        try:
            text = await build_digest(token, storage.get_login(uid))
            await context.bot.send_message(
                uid, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
            )
        except Exception:
            pass
        await asyncio.sleep(0.5)  # be nice to Telegram and GitHub limits


# ---------- NOTIFICATIONS ----------

def _html_url(api_url: str) -> str:
    return (
        api_url.replace("https://api.github.com/repos/", "https://github.com/")
        .replace("/pulls/", "/pull/")
    )


async def notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = storage.get_token(update.effective_user.id)
    if not token:
        await update.message.reply_text("Please /login first.")
        return
    r = await gh.get("/notifications", token, {"per_page": 10})
    if r.status_code != 200:
        await update.message.reply_text("Could not load notifications. Try /logout then /login.")
        return
    items = r.json()
    if not items:
        await update.message.reply_text("📭 No unread notifications.")
        return
    lines = ["🔔 <b>Unread notifications</b>\n"]
    for n in items:
        s = n["subject"]
        url = _html_url(s["url"]) if s.get("url") else n["repository"]["html_url"]
        lines.append(
            f"• <a href=\"{url}\">{esc(s['title'][:70])}</a>\n"
            f"  📦 {esc(n['repository']['full_name'])} · {esc(n['reason'])}"
        )
    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )