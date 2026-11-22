from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
import github_api as gh
import storage
from config import ADMIN_ID

HELP_TEXT = (
    "<b>DevHub Assistant commands</b>\n\n"
    "<b>Explore</b>\n"
    "/user &lt;username&gt; - profile info\n"
    "/repo &lt;owner/name&gt; - repo details\n"
    "/search &lt;query&gt; - search repos\n"
    "/trending [language] - trending repos\n"
    "/release &lt;owner/name&gt; - latest release\n"
    "/issues &lt;owner/name&gt; - open issues\n"
    "/prs &lt;owner/name&gt; - open pull requests\n"
    "/goodfirst [language] - good first issues\n"
    "/stats &lt;username&gt; - top languages and stars\n"
    "/card &lt;username&gt; [theme] - stats card in 6 themes\n\n"
    "<b>Account</b>\n"
    "/login - connect GitHub\n"
    "/logout - disconnect GitHub\n"
    "/newrepo - create a repository\n"
    "/newissue &lt;owner/name&gt; &lt;title&gt; - create an issue\n"
    "/gist - create a gist (reply to a message or send text after command)\n"
    "/star &lt;owner/name&gt; - star a repo\n"
    "/unstar &lt;owner/name&gt; - unstar a repo\n\n"
    "<b>Alerts</b>\n"
    "/watch &lt;owner/name&gt; - live alerts in this chat\n"
    "/unwatch &lt;owner/name&gt; - stop alerts\n"
    "/watching - list watched repos\n"
    "/digest [on|off] - daily activity summary\n"
    "/notifications - unread GitHub notifications"
)


def esc(s) -> str:
    s = "" if s is None else str(s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to <b>DevHub Assistant</b>!\n"
        "Your GitHub companion inside Telegram.\n\n"
        "Send /help to see everything I can do.",
        parse_mode=ParseMode.HTML,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_ID or str(update.effective_user.id) != ADMIN_ID:
        await update.effective_message.reply_text("This command is for the bot administrator only.")
        return

    count, rows = storage.get_bot_users()
    lines = [f"<b>Total users: {count}</b>"]
    for telegram_id, username, first_name, last_name in rows:
        name = " ".join(part for part in (first_name, last_name) if part) or "-"
        handle = f"@{username}" if username else "no username"
        lines.append(f"<code>{telegram_id}</code> — {esc(name)} ({esc(handle)})")

    # Keep each Telegram message below its limit without splitting HTML tags.
    chunk = lines[0]
    for line in lines[1:]:
        if len(chunk) + len(line) + 1 > 3900:
            await update.effective_message.reply_text(chunk, parse_mode=ParseMode.HTML)
            chunk = line
        else:
            chunk += "\n" + line
    await update.effective_message.reply_text(chunk, parse_mode=ParseMode.HTML)


def _token_for(update):
    return storage.get_token(update.effective_user.id)


async def user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /user <username>")
        return
    r = await gh.get(f"/users/{context.args[0]}", _token_for(update))
    if r.status_code != 200:
        await update.message.reply_text("User not found.")
        return
    d = r.json()
    text = (
        f"👤 <b>{esc(d['login'])}</b> ({esc(d.get('name') or '-')})\n"
        f"📝 {esc(d.get('bio') or '-')}\n"
        f"📍 {esc(d.get('location') or '-')}\n"
        f"📦 Repos: {d['public_repos']}\n"
        f"👥 Followers: {d['followers']} | Following: {d['following']}\n"
        f"🔗 {d['html_url']}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def repo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or "/" not in context.args[0]:
        await update.message.reply_text("Usage: /repo <owner/name>")
        return
    r = await gh.get(f"/repos/{context.args[0]}", _token_for(update))
    if r.status_code != 200:
        await update.message.reply_text("Repository not found.")
        return
    d = r.json()
    lic = (d.get("license") or {}).get("spdx_id") or "-"
    text = (
        f"📦 <b>{esc(d['full_name'])}</b>\n"
        f"📝 {esc(d.get('description') or '-')}\n\n"
        f"⭐ {d['stargazers_count']}  🍴 {d['forks_count']}  🐞 {d['open_issues_count']}\n"
        f"💻 {esc(d.get('language') or '-')}  📄 {esc(lic)}\n"
        f"🕒 Updated: {d['pushed_at'][:10]}\n"
        f"🔗 {d['html_url']}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /search <query>")
        return
    q = " ".join(context.args)
    r = await gh.get(
        "/search/repositories",
        _token_for(update),
        {"q": q, "sort": "stars", "order": "desc", "per_page": 8},
    )
    items = r.json().get("items", []) if r.status_code == 200 else []
    if not items:
        await update.message.reply_text("No results.")
        return
    lines = [f"🔎 <b>Results for:</b> {esc(q)}\n"]
    for i in items:
        lines.append(
            f"• <a href=\"{i['html_url']}\">{esc(i['full_name'])}</a> ⭐{i['stargazers_count']}\n"
            f"  {esc((i.get('description') or '')[:90])}"
        )
    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )


async def trending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    q = f"created:>{since}"
    if context.args:
        q += f" language:{context.args[0]}"
    r = await gh.get(
        "/search/repositories",
        _token_for(update),
        {"q": q, "sort": "stars", "order": "desc", "per_page": 8},
    )
    items = r.json().get("items", []) if r.status_code == 200 else []
    if not items:
        await update.message.reply_text("Nothing found.")
        return
    lines = ["🔥 <b>Trending this week</b>\n"]
    for i in items:
        lines.append(
            f"• <a href=\"{i['html_url']}\">{esc(i['full_name'])}</a> ⭐{i['stargazers_count']}\n"
            f"  {esc((i.get('description') or '')[:90])}"
        )
    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )


async def release(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or "/" not in context.args[0]:
        await update.message.reply_text("Usage: /release <owner/name>")
        return
    r = await gh.get(f"/repos/{context.args[0]}/releases/latest", _token_for(update))
    if r.status_code != 200:
        await update.message.reply_text("No release found.")
        return
    d = r.json()
    body = esc((d.get("body") or "")[:600])
    await update.message.reply_text(
        f"🚀 <b>{esc(d.get('name') or d['tag_name'])}</b> ({esc(d['tag_name'])})\n"
        f"📅 {d['published_at'][:10]}\n\n{body}\n\n🔗 {d['html_url']}",
        parse_mode=ParseMode.HTML,
    )


async def _list_items(update, context, kind):
    if not context.args or "/" not in context.args[0]:
        await update.message.reply_text(f"Usage: /{kind} <owner/name>")
        return
    repo_name = context.args[0]
    path = "pulls" if kind == "prs" else "issues"
    r = await gh.get(
        f"/repos/{repo_name}/{path}",
        _token_for(update),
        {"state": "open", "per_page": 10},
    )
    if r.status_code != 200:
        await update.message.reply_text("Repository not found.")
        return
    items = r.json()
    if kind == "issues":
        items = [i for i in items if "pull_request" not in i]
    if not items:
        await update.message.reply_text("Nothing open 🎉")
        return
    lines = [f"📋 <b>Open {kind} in {esc(repo_name)}</b>\n"]
    for i in items:
        lines.append(f"• <a href=\"{i['html_url']}\">#{i['number']}</a> {esc(i['title'][:80])}")
    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )


async def issues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _list_items(update, context, "issues")


async def prs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _list_items(update, context, "prs")


async def goodfirst(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = 'label:"good first issue" state:open is:issue'
    if context.args:
        q += f" language:{context.args[0]}"
    r = await gh.get(
        "/search/issues",
        _token_for(update),
        {"q": q, "sort": "created", "order": "desc", "per_page": 8},
    )
    items = r.json().get("items", []) if r.status_code == 200 else []
    if not items:
        await update.message.reply_text("Nothing found.")
        return
    lines = ["🌱 <b>Good first issues</b>\n"]
    for i in items:
        repo_name = i["repository_url"].replace("https://api.github.com/repos/", "")
        lines.append(
            f"• <a href=\"{i['html_url']}\">{esc(i['title'][:70])}</a>\n  📦 {esc(repo_name)}"
        )
    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /stats <username>")
        return
    r = await gh.get(
        f"/users/{context.args[0]}/repos",
        _token_for(update),
        {"per_page": 100, "type": "owner"},
    )
    if r.status_code != 200:
        await update.message.reply_text("User not found.")
        return
    repos = [x for x in r.json() if not x["fork"]]
    stars = sum(x["stargazers_count"] for x in repos)
    langs = {}
    for x in repos:
        if x.get("language"):
            langs[x["language"]] = langs.get(x["language"], 0) + 1
    top = sorted(langs.items(), key=lambda kv: kv[1], reverse=True)[:5]
    lang_txt = "\n".join(f"  • {esc(k)}: {v}" for k, v in top) or "  -"
    await update.message.reply_text(
        f"📊 <b>Stats for {esc(context.args[0])}</b>\n\n"
        f"📦 Original repos: {len(repos)}\n"
        f"⭐ Total stars: {stars}\n"
        f"💻 Top languages:\n{lang_txt}",
        parse_mode=ParseMode.HTML,
    )
