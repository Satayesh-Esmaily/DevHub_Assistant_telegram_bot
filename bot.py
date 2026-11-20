import logging
from telegram.ext import ApplicationBuilder, CommandHandler
from config import BOT_TOKEN
import storage
from handlers import basic, auth_write

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


def main():
    storage.init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Step 1: read-only
    app.add_handler(CommandHandler("start", basic.start))
    app.add_handler(CommandHandler("help", basic.help_cmd))
    app.add_handler(CommandHandler("user", basic.user))
    app.add_handler(CommandHandler("repo", basic.repo))
    app.add_handler(CommandHandler("search", basic.search))
    app.add_handler(CommandHandler("trending", basic.trending))
    app.add_handler(CommandHandler("release", basic.release))
    app.add_handler(CommandHandler("issues", basic.issues))
    app.add_handler(CommandHandler("prs", basic.prs))
    app.add_handler(CommandHandler("goodfirst", basic.goodfirst))
    app.add_handler(CommandHandler("stats", basic.stats))

    # Step 2: auth + write
    app.add_handler(CommandHandler("login", auth_write.login))
    app.add_handler(CommandHandler("logout", auth_write.logout))
    app.add_handler(CommandHandler("star", auth_write.star))
    app.add_handler(CommandHandler("unstar", auth_write.unstar))
    app.add_handler(CommandHandler("newissue", auth_write.newissue))
    app.add_handler(CommandHandler("gist", auth_write.gist))
    app.add_handler(auth_write.newrepo_conv)

    app.run_polling()


if __name__ == "__main__":
    main()