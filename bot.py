# ==============================
# IMPORT
# ==============================
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import os
import re
import time
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


# ==============================
# CONFIG
# ==============================
TOKEN = os.getenv("BOT_TOKEN")
RESTORE_SECONDS = 2 * 60 * 60  # 2 hours


# ==============================
# STORAGE
# ==============================
players = {}          # InGameName -> @TelegramName
last_positions = {}   # InGameName -> last positions
buildings = {i: [] for i in range(8)}


# ==============================
# MINI HTTP SERVER (RENDER)
# ==============================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")


def start_http_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()


# ==============================
# UTILITY
# ==============================
def format_time(seconds):
    seconds = max(0, seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}:{m:02d}"


def get_player_from_telegram(username):
    for ingame, tg in players.items():
        if tg == username:
            return ingame
    return None


async def schedule_restore(app, telegram, expires_at):
    delay = expires_at - time.time()
    if delay > 0:
        await asyncio.sleep(delay)
    await app.bot.send_message(chat_id=telegram, text=f"{telegram} car restored")


def remove_player_from_all_buildings(ingame):
    for b in buildings.values():
        b[:] = [e for e in b if e["player"] != ingame]


# ==============================
# COMMANDS
# ==============================
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.delete()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "/register InGameName @TelegramName\n"
            "/remove InGameName\n"
            "/123 /1-3 /-45\n"
            "/list\n"
            "/lX\n"
            "/bX InGame1, InGame2\n"
            "/reset\n"
            "/call text\n"
            "/xall text\n"
            "/h x:xx x:xx | res | reset"
        )
    )


async def reg
