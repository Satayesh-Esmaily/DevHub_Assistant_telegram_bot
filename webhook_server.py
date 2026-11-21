import hashlib
import hmac
import json
import logging

from aiohttp import web
from telegram.constants import ParseMode

from config import WEBHOOK_SECRET
from handlers.basic import esc

log = logging.getLogger(__name__)

# events requested when creating the webhook
HOOK_EVENTS = ["push", "issues", "pull_request", "watch", "release", "fork", "workflow_run"]


def format_event(event: str, p: dict):
    repo = esc(p.get("repository", {}).get("full_name", ""))
    sender = esc(p.get("sender", {}).get("login", ""))
    action = p.get("action")

    if event == "ping":
        return f"🔗 Webhook connected for <b>{repo}</b>"

    if event == "push":
        commits = p.get("commits", [])
        if not commits:
            return None
        branch = esc(p["ref"].split("/", 2)[-1])
        lines = [f"📌 <b>{repo}</b> · {len(commits)} new commit(s) on <code>{branch}</code> by {sender}"]
        for c in commits[:3]:
            msg = esc(c["message"].splitlines()[0][:80])
            lines.append(f"• <a href=\"{c['url']}\">{c['id'][:7]}</a> {msg}")
        if len(commits) > 3:
            lines.append(f"… and {len(commits) - 3} more")
        return "\n".join(lines)

    if event == "issues" and action in ("opened", "closed", "reopened"):
        i = p["issue"]
        icon = {"opened": "🐞", "closed": "✅", "reopened": "🔄"}[action]
        return (
            f"{icon} Issue {action} in <b>{repo}</b> by {sender}\n"
            f"<a href=\"{i['html_url']}\">#{i['number']}</a> {esc(i['title'][:100])}"
        )

    if event == "pull_request" and action in ("opened", "closed", "reopened"):
        pr = p["pull_request"]
        if action == "closed" and pr.get("merged"):
            head, icon = "merged", "🟣"
        else:
            head = action
            icon = {"opened": "🔀", "closed": "🚫", "reopened": "🔄"}[action]
        return (
            f"{icon} PR {head} in <b>{repo}</b> by {sender}\n"
            f"<a href=\"{pr['html_url']}\">#{pr['number']}</a> {esc(pr['title'][:100])}"
        )

    if event == "watch" and action == "started":
        count = p["repository"].get("stargazers_count", "?")
        return f"⭐ <b>{sender}</b> starred <b>{repo}</b> (total: {count})"

    if event == "fork":
        f = p["forkee"]
        return f"🍴 <b>{sender}</b> forked <b>{repo}</b>\n<a href=\"{f['html_url']}\">{esc(f['full_name'])}</a>"

    if event == "release" and action == "published":
        r = p["release"]
        return (
            f"🚀 New release in <b>{repo}</b>: "
            f"<a href=\"{r['html_url']}\">{esc(r.get('name') or r['tag_name'])}</a>"
        )

    if event == "workflow_run" and action == "completed":
        w = p["workflow_run"]
        concl = w.get("conclusion")
        icon = {"success": "✅", "failure": "❌", "cancelled": "⚪"}.get(concl, "ℹ️")
        return (
            f"{icon} CI <b>{esc(w['name'])}</b> {esc(concl)} in <b>{repo}</b>\n"
            f"Branch: <code>{esc(w['head_branch'])}</code> · <a href=\"{w['html_url']}\">details</a>"
        )

    return None


async def handle_webhook(request: web.Request):
    body = await request.read()

    sig = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return web.Response(status=401, text="bad signature")

    try:
        chat_id = int(request.match_info["chat_id"])
        payload = json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return web.Response(status=400, text="bad request")

    text = format_event(request.headers.get("X-GitHub-Event", ""), payload)
    if text:
        try:
            await request.app["bot"].send_message(
                chat_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
            )
        except Exception as e:
            log.warning("Could not send to %s: %s", chat_id, e)
    return web.Response(text="ok")


def make_app(bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/webhook/{chat_id}", handle_webhook)
    app.router.add_get("/", lambda r: web.Response(text="RepoPilot is running"))
    return app