import os
import json
import gspread
import logging
from flask import Flask, request
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# ─────────────────── 환경 변수 로드 ───────────────────
BOT_TOKEN = os.environ["BOT_TOKEN"]
SHEET_ID = os.environ["SHEET_ID"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]
creds_dict = json.loads(os.environ["GOOGLE_JSON"])

# ─────────────────── 구글 시트 연결 ───────────────────
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SHEET_ID).sheet1

# ─────────────────── 텔레그램 핸들러 ───────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("안녕하세요! Jiseon Bot입니다.")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

# ─────────────────── Flask 앱 설정 ───────────────────
app = Flask(__name__)

@app.route("/")
def index():
    return "📡 Jiseon Bot is running."

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        telegram_app.update_queue.put_nowait(update)
        return "OK"

# ─────────────────── 텔레그램 앱 구성 ───────────────────
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# ─────────────────── 메인 진입점 ───────────────────
async def main():
    await telegram_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}")
    telegram_app.run_polling()  # 웹훅만 쓸 경우 이 줄은 생략 가능

if __name__ == "__main__":
    import nest_asyncio
    import asyncio
    nest_asyncio.apply()
    asyncio.run(main())

    # Flask 앱 실행
    app.run(host="0.0.0.0", port=10000)
