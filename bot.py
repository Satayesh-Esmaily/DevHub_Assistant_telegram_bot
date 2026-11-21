import datetime as dt
import logging

from aiohttp import web
from telegram.ext import ApplicationBuilder, CommandHandler

import storage
import webhook_server
from config import BOT_TOKEN, PORT, DIGEST_HOUR_UTC
from handlers import basic, auth_write, watch

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


async def post_init(app):
    runner = web.AppRunner(webhook_server.make_app(app.bot))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    app.bot_data["runner"] = runner
    logging.info("Webhook server listening on port %s", PORT)


async def post_shutdown(app):
    runner = app.bot_data.get("runner")
    if runner:
        await runner.cleanup()


def main():
    storage.init_db()
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Step 1: read-only
    for name, fn in [
        ("start", basic.start), ("help", basic.help_cmd), ("user", basic.user),
        ("repo", basic.repo), ("search", basic.search), ("trending", basic.trending),
        ("release", basic.release), ("issues", basic.issues), ("prs", basic.prs),
        ("goodfirst", basic.goodfirst), ("stats", basic.stats),
    ]:
        app.add_handler(CommandHandler(name, fn))

    # Step 2: auth + write
    for name, fn in [
        ("login", auth_write.login), ("logout", auth_write.logout),
        ("star", auth_write.star), ("unstar", auth_write.unstar),
        ("newissue", auth_write.newissue), ("gist", auth_write.gist),
    ]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(auth_write.newrepo_conv)

    # Step 3: watch, digest, notifications
    for name, fn in [
        ("watch", watch.watch), ("unwatch", watch.unwatch), ("watching", watch.watching),
        ("digest", watch.digest), ("notifications", watch.notifications),
    ]:
        app.add_handler(CommandHandler(name, fn))

    app.job_queue.run_daily(
        watch.send_daily_digests,
        time=dt.time(hour=DIGEST_HOUR_UTC, minute=0, tzinfo=dt.timezone.utc),
    )

    app.run_polling()


if __name__ == "__main__":
    main()