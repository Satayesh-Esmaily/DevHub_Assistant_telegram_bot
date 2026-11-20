import asyncio
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
import github_api as gh
import storage
from config import GITHUB_CLIENT_ID
from handlers.basic import esc

DEVICE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
SCOPES = "public_repo gist"  # for private repos use "repo gist"


# ---------- LOGIN (Device Flow) ----------

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if storage.get_token(uid):
        await update.message.reply_text(
            f"You are already logged in as {storage.get_login(uid)}. Use /logout first to switch."
        )
        return

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            DEVICE_URL,
            data={"client_id": GITHUB_CLIENT_ID, "scope": SCOPES},
            headers={"Accept": "application/json"},
        )
    if r.status_code != 200:
        await update.message.reply_text("Could not start login. Try again later.")
        return

    d = r.json()
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Open GitHub", url=d["verification_uri"])]]
    )
    await update.message.reply_text(
        f"🔐 <b>Connect GitHub</b>\n\n"
        f"1. Open the link below\n"
        f"2. Enter this code: <code>{d['user_code']}</code>\n\n"
        f"I'll wait for you (expires in {d['expires_in'] // 60} min).",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    context.application.create_task(
        _poll_token(update, context, d["device_code"], d.get("interval", 5), d["expires_in"])
    )


async def _poll_token(update, context, device_code, interval, expires_in):
    uid = update.effective_user.id
    waited = 0
    async with httpx.AsyncClient(timeout=15) as client:
        while waited < expires_in:
            await asyncio.sleep(interval)
            waited += interval
            r = await client.post(
                TOKEN_URL,
                data={
                    "client_id": GITHUB_CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={"Accept": "application/json"},
            )
            data = r.json()
            if "access_token" in data:
                token = data["access_token"]
                me = await gh.get("/user", token)
                login_name = me.json().get("login", "unknown")
                storage.save_token(uid, login_name, token)
                await context.bot.send_message(
                    uid, f"✅ Connected as <b>{esc(login_name)}</b>!", parse_mode=ParseMode.HTML
                )
                return
            err = data.get("error")
            if err == "slow_down":
                interval = data.get("interval", interval + 5)
            elif err in ("expired_token", "access_denied"):
                await context.bot.send_message(uid, "❌ Login failed or cancelled. Use /login again.")
                return
    await context.bot.send_message(uid, "⌛ Login expired. Use /login again.")


async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage.delete_user(update.effective_user.id)
    await update.message.reply_text(
        "👋 Disconnected. To fully revoke access, go to GitHub → Settings → Applications."
    )


def _need_login(update):
    token = storage.get_token(update.effective_user.id)
    return token


# ---------- STAR / UNSTAR ----------

async def star(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = _need_login(update)
    if not token:
        await update.message.reply_text("Please /login first.")
        return
    if not context.args or "/" not in context.args[0]:
        await update.message.reply_text("Usage: /star <owner/name>")
        return
    r = await gh.put(f"/user/starred/{context.args[0]}", token)
    await update.message.reply_text("⭐ Starred!" if r.status_code == 204 else "Failed. Check the repo name.")


async def unstar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = _need_login(update)
    if not token:
        await update.message.reply_text("Please /login first.")
        return
    if not context.args or "/" not in context.args[0]:
        await update.message.reply_text("Usage: /unstar <owner/name>")
        return
    r = await gh.delete(f"/user/starred/{context.args[0]}", token)
    await update.message.reply_text("Removed star." if r.status_code == 204 else "Failed. Check the repo name.")


# ---------- NEW ISSUE ----------

async def newissue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = _need_login(update)
    if not token:
        await update.message.reply_text("Please /login first.")
        return
    if len(context.args) < 2 or "/" not in context.args[0]:
        await update.message.reply_text("Usage: /newissue <owner/name> <title>")
        return
    repo_name = context.args[0]
    title = " ".join(context.args[1:])
    r = await gh.post(f"/repos/{repo_name}/issues", token, {"title": title})
    if r.status_code == 201:
        await update.message.reply_text(f"✅ Issue created:\n{r.json()['html_url']}")
    else:
        await update.message.reply_text("Failed to create issue. Check repo name and permissions.")


# ---------- GIST ----------

async def gist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = _need_login(update)
    if not token:
        await update.message.reply_text("Please /login first.")
        return

    content = None
    if update.message.reply_to_message and update.message.reply_to_message.text:
        content = update.message.reply_to_message.text
    elif context.args:
        content = update.message.text.split(maxsplit=1)[1]

    if not content:
        await update.message.reply_text(
            "Usage: reply to a message with /gist, or send /gist <your code or text>"
        )
        return

    r = await gh.post(
        "/gists",
        token,
        {
            "description": "Created with DevHub Assistant bot",
            "public": False,
            "files": {"snippet.txt": {"content": content}},
        },
    )
    if r.status_code == 201:
        await update.message.reply_text(f"✅ Secret gist created:\n{r.json()['html_url']}")
    else:
        await update.message.reply_text("Failed to create gist.")


# ---------- NEW REPO (conversation) ----------

NAME, DESC, VIS, CONFIRM = range(4)


async def newrepo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _need_login(update):
        await update.message.reply_text("Please /login first.")
        return ConversationHandler.END
    await update.message.reply_text("📦 Repository name? (send /cancel to stop)")
    return NAME


async def newrepo_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip().replace(" ", "-")
    context.user_data["repo_name"] = name
    await update.message.reply_text("📝 Short description? (send - to skip)")
    return DESC


async def newrepo_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data["repo_desc"] = "" if text == "-" else text
    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🌍 Public", callback_data="vis_public"),
            InlineKeyboardButton("🔒 Private", callback_data="vis_private"),
        ]]
    )
    await update.message.reply_text("Visibility?", reply_markup=kb)
    return VIS


async def newrepo_vis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["repo_private"] = q.data == "vis_private"
    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ Create", callback_data="confirm_yes"),
            InlineKeyboardButton("❌ Cancel", callback_data="confirm_no"),
        ]]
    )
    d = context.user_data
    await q.edit_message_text(
        f"<b>Create this repo?</b>\n\n"
        f"Name: <code>{esc(d['repo_name'])}</code>\n"
        f"Description: {esc(d['repo_desc'] or '-')}\n"
        f"Visibility: {'Private' if d['repo_private'] else 'Public'}\n"
        f"README: yes",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    return CONFIRM


async def newrepo_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "confirm_no":
        await q.edit_message_text("Cancelled.")
        return ConversationHandler.END

    token = storage.get_token(update.effective_user.id)
    d = context.user_data
    r = await gh.post(
        "/user/repos",
        token,
        {
            "name": d["repo_name"],
            "description": d["repo_desc"],
            "private": d["repo_private"],
            "auto_init": True,
        },
    )
    if r.status_code == 201:
        await q.edit_message_text(f"✅ Repository created:\n{r.json()['html_url']}")
    else:
        msg = r.json().get("message", "Unknown error")
        await q.edit_message_text(f"❌ Failed: {msg}")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


newrepo_conv = ConversationHandler(
    entry_points=[CommandHandler("newrepo", newrepo_start)],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, newrepo_name)],
        DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, newrepo_desc)],
        VIS: [CallbackQueryHandler(newrepo_vis, pattern="^vis_")],
        CONFIRM: [CallbackQueryHandler(newrepo_confirm, pattern="^confirm_")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)