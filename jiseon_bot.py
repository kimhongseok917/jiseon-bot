import os
import asyncio

from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# 환경변수로부터 읽어오기
BOT_TOKEN = os.environ["BOT_TOKEN"]
SHEET_ID = os.environ["SHEET_ID"]

app = Flask(__name__)

# 1) Application 빌드
application = Application.builder().token(BOT_TOKEN).build()

# 2) application.bot 을 bot 변수로 참조해두면 편합니다
bot = application.bot

# 봇 명령어 핸들러 예시
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("안녕하세요!")

application.add_handler(CommandHandler("start", start))


@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    # Telegram에서 오는 JSON을 파싱
    data = request.get_json(force=True)

    # Update 객체 생성 (bot 변수를 제대로 참조)
    update = Update.de_json(data, bot)

    try:
        # 비동기 핸들러 실행을 동기처럼 처리
        asyncio.run(application.process_update(update))
        return "OK", 200
    except Exception as e:
        import traceback
        print("❌ Webhook handler exception:", e)
        traceback.print_exc()
        return "Internal Server Error", 500


@app.route("/health")
def health():
    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    # 개발용 서버입니다. Render에선 WSGI 서버(gunicorn)로 띄울 거예요.
    app.run(host="0.0.0.0", port=port)
