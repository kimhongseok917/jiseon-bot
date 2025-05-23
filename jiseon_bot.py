from flask import Flask
import threading, asyncio, schedule
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from zoneinfo import ZoneInfo
import os, json

# ── 환경변수 로드 ──
BOT_TOKEN   = os.environ["BOT_TOKEN"]
SHEET_ID    = os.environ["SHEET_ID"]
creds_dict  = json.loads(os.environ["GOOGLE_JSON"])

# ── Google Sheet 연결 ──
scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
creds    = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client   = gspread.authorize(creds)
sheet    = client.open_by_key(SHEET_ID).sheet1

# ── Flask 앱 (헬스체크) ──
app = Flask(__name__)
@app.route("/health")
def health():
    return "OK", 200

# ── 체크리스트 문항 ──
questions = [
    "1. 장 시작 10분은 지났나요? (Y/N)",
    "2. 갭이 8% 이하에서 출발했나요? (Y/N)",
    "3. 테마군 상승 또는 분당 100억 이상의 거래대금 발생 종목인가요? (Y/N)",
    "4. 일봉상 신고가 또는 박스권 돌파인가요? (Y/N)",
    "5. 1분봉 상 25억 이상의 거래대금이 2번 이상 발생했나요? (Y/N)",
    "6. 돌파 시작 3분 이내 10% 이상 급등한 종목은 아닌가요? (Y/N)",
    "7. 1분봉 상 박스권을 만들었나요? (Y/N)",
    "8. 1분봉 상 급등/급락을 반복하지 않나요? (Y/N)",
    "9. 단기 전고점 대비 -4.5% 이상 하락하지 않았나요? (Y/N)",
    "10. 좋은 뉴스가 발생했나요? (Y/N)"
]
user_states = {}

# ── Telegram 봇 핸들러 ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    stock = "미입력" if not context.args else " ".join(context.args)
    user_states[uid] = {'step':0, 'answers':[], 'stock':stock}
    await update.message.reply_text(f"🧠 [{stock}] 체크리스트 시작\n{questions[0]}")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text.strip().upper()
    if uid not in user_states:
        return await update.message.reply_text("👉 먼저 /start [종목명] 입력해주세요.")
    if txt not in ['Y','N']:
        return await update.message.reply_text("Y 또는 N 으로 답해주세요.")
    data = user_states[uid]
    data['answers'].append(txt)
    data['step'] += 1
    if data['step'] < len(questions):
        return await update.message.reply_text(questions[data['step']])

    yes_count = sum(1 for a in data['answers'] if a=='Y')
    result    = "✅ 진입 가능" if yes_count >= 7 else "❌ 진입 보류"
    now       = datetime.now(ZoneInfo("Asia/Seoul"))
    date_str  = now.strftime("%Y-%m-%d")
    time_str  = now.strftime("%H:%M")

    sheet.append_row([date_str, time_str, data['stock']] + data['answers'] + [yes_count, result])
    await update.message.reply_text(f"{result} ({yes_count}/10) 기록 완료!")
    del user_states[uid]

def run_bot():
    import nest_asyncio
    nest_asyncio.apply()

    # ─── Polling 스레드 시작 로그 ───
    print("🟢 [지선 봇] Polling 스레드 시작")
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle))

    # ─── 실제 Telegram Polling 실행 로그 ───
    print("🟢 [지선 봇] Telegram Polling 실행 중…")
    asyncio.run(app_bot.run_polling())


if __name__ == "__main__":
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=10000)
