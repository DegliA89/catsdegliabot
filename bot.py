from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import re
import time
import asyncio

import os
TOKEN = os.getenv("BOT_TOKEN")
RESTORE_SECONDS = 2 * 60 * 60  # 2 hours

# InGameName -> Telegram username
players = {}

# InGameName -> last positions (for "-")
last_positions = {}

# Building -> list of entries {player, expires_at(optional)}
buildings = {i: [] for i in range(8)}


# --------------------------------------------------
# Utility
# --------------------------------------------------
def format_time(seconds):
    if seconds < 0:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}:{m:02d}"


async def schedule_restore(app, telegram, expires_at):
    delay = expires_at - time.time()
    if delay > 0:
        await asyncio.sleep(delay)
    await app.bot.send_message(
        chat_id=telegram,
        text=f"{telegram} car restored"
    )


def get_player_from_telegram(username):
    for ingame, tg in players.items():
        if tg == username:
            return ingame
    return None


# --------------------------------------------------
# /help
# --------------------------------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/register InGameName @TelegramName\n"
        "Register a player.\n\n"
        "/remove InGameName\n"
        "Remove a player.\n\n"
        "/123 /1-3 /-45 (@TelegramName)\n"
        "Assign buildings. '-' keeps previous value.\n\n"
        "/list\n"
        "Show all buildings.\n\n"
        "/lX\n"
        "Show building X (0–7).\n\n"
        "/bX InGameName1, InGameName2\n"
        "Add players to building X.\n\n"
        "/reset\n"
        "Reset all buildings.\n\n"
        "/call [text]\n"
        "Mention all registered players in the group.\n\n"
        "/xall text\n"
        "Send a private message to all players.\n\n"
        "/h x:xx x:xx x:xx | - | res | reset\n"
        "Manage timers for building 0."
    )


# --------------------------------------------------
# /register
# --------------------------------------------------
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /register InGameName @TelegramName")
        return

    ingame, telegram = context.args
    players[ingame] = telegram
    last_positions[ingame] = []

    await update.message.reply_text(f"Player {ingame} registered.")


# --------------------------------------------------
# /remove
# --------------------------------------------------
async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        return

    ingame = context.args[0]
    players.pop(ingame, None)
    last_positions.pop(ingame, None)

    for b in buildings.values():
        b[:] = [e for e in b if e["player"] != ingame]

    await update.message.reply_text(f"Player {ingame} removed.")


# --------------------------------------------------
# /reset
# --------------------------------------------------
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for i in range(8):
        buildings[i].clear()

    await update.message.reply_text(
        "All buildings have been reset.\n"
        "Registered players were not removed.\n\n"
        "list restored"
    )


# --------------------------------------------------
# /abc with "-" support
# --------------------------------------------------
async def number_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    match = re.match(r"^/([0-7\-]{3,})(?:\s+(@\w+))?$", text)
    if not match:
        return

    seq = match.group(1)
    target = match.group(2)

    if target:
        ingame = get_player_from_telegram(target)
    else:
        sender = update.message.from_user.username
        ingame = get_player_from_telegram(f"@{sender}") if sender else None

    if not ingame:
        return

    prev = last_positions.get(ingame, [])
    resolved = []

    for i, ch in enumerate(seq):
        if ch == "-" and i < len(prev):
            resolved.append(prev[i])
        elif ch != "-":
            resolved.append(int(ch))

    last_positions[ingame] = resolved

    for pos in resolved:
        entry = {"player": ingame}

        if pos == 0:
            expires = time.time() + RESTORE_SECONDS
            entry["expires_at"] = expires
            context.application.create_task(
                schedule_restore(context.application, players[ingame], expires)
            )

        buildings[pos].append(entry)


# --------------------------------------------------
# /list
# --------------------------------------------------
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = time.time()
    msg = []

    for i in range(8):
        msg.append(f"----- {i} -----")
        grouped = {}

        for e in buildings[i]:
            grouped.setdefault(e["player"], []).append(e)

        for p, entries in grouped.items():
            tg = players[p].replace("@", "")
            line = f"{len(entries)}x {p} ({tg})"

            if i == 0:
                times = [
                    format_time(int(e["expires_at"] - now))
                    for e in entries if "expires_at" in e
                ]
                if times:
                    line += " " + " ".join(times)

            msg.append(line)
        msg.append("")

    await update.message.reply_text("\n".join(msg))


# --------------------------------------------------
# /lX
# --------------------------------------------------
async def lx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not re.match(r"^/l[0-7]$", text):
        return

    x = int(text[2])
    now = time.time()
    msg = [f"----- {x} -----"]

    grouped = {}
    for e in buildings[x]:
        grouped.setdefault(e["player"], []).append(e)

    for p, entries in grouped.items():
        tg = players[p].replace("@", "")
        line = f"{len(entries)}x {p} ({tg})"

        if x == 0:
            times = [
                format_time(int(e["expires_at"] - now))
                for e in entries if "expires_at" in e
            ]
            if times:
                line += " " + " ".join(times)

        msg.append(line)

    await update.message.reply_text("\n".join(msg))


# --------------------------------------------------
# /bX
# --------------------------------------------------
async def bx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    match = re.match(r"^/b([0-7])\s+(.+)$", text)
    if not match:
        return

    x = int(match.group(1))
    names = [n.strip() for n in match.group(2).split(",")]

    for name in names:
        if name in players:
            count = sum(1 for e in buildings[x] if e["player"] == name)
            if count < 2:
                entry = {"player": name}
                if x == 0:
                    expires = time.time() + RESTORE_SECONDS
                    entry["expires_at"] = expires
                    context.application.create_task(
                        schedule_restore(context.application, players[name], expires)
                    )
                buildings[x].append(entry)


# --------------------------------------------------
# /call
# --------------------------------------------------
async def call(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mentions = ", ".join(players.values())
    sender = update.message.from_user.username or "Unknown"
    text = " ".join(context.args)

    msg = mentions
    if text:
        msg += f"\n\n{sender}:\n{text}"

    await update.message.reply_text(msg)


# --------------------------------------------------
# /xall
# --------------------------------------------------
async def xall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return

    sender = update.message.from_user.username or "Unknown"
    text = " ".join(context.args)

    for tg in players.values():
        await context.application.bot.send_message(
            chat_id=tg,
            text=f"{sender}:\n{text}"
        )


# --------------------------------------------------
# /h timers
# --------------------------------------------------
async def h_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.message.from_user.username
    if not sender:
        return

    ingame = get_player_from_telegram(f"@{sender}")
    if not ingame:
        return

    if not context.args:
        return

    if context.args[0] == "reset":
        buildings[0] = [e for e in buildings[0] if e["player"] != ingame]
        return

    timers = [e for e in buildings[0] if e["player"] == ingame]

    for i, arg in enumerate(context.args):
        if i >= len(timers):
            break

        if arg == "-":
            continue
        if arg == "res":
            timers[i]["expires_at"] = time.time()
        else:
            h, m = map(int, arg.split(":"))
            timers[i]["expires_at"] = time.time() + h * 3600 + m * 60


# --------------------------------------------------
# MAIN
# --------------------------------------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("call", call))
    app.add_handler(CommandHandler("xall", xall))
    app.add_handler(CommandHandler("h", h_command))

    app.add_handler(MessageHandler(filters.Regex(r"^/l[0-7]$"), lx))
    app.add_handler(MessageHandler(filters.Regex(r"^/b[0-7]"), bx))
    app.add_handler(MessageHandler(filters.Regex(r"^/[0-7\-]{3,}"), number_command))

    app.run_polling()


if __name__ == "__main__":
    main()


