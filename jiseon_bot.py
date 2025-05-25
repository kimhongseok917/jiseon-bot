from flask import Flask
import threading, asyncio, schedule
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from zoneinfo import ZoneInfo
import os, json

# ── 환경변수 로드 ──
BOT_TOKEN  = os.environ["7882472825:AAHoJveOycg7GYVNWI7umKR9ZOz5xv4xnA4"]
SHEET_ID   = os.environ["1jbYjQlCwKAj2nzPuDp1BUm9uDK_5q16t5bA7ovoyrew"]
creds_dict = json.loads(os.environ["pjbrich-893b658b2a25.JSON"])

# ── Google Sheet 연결 ──
scope   = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
creds   = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client  = gspread.authorize(creds)
sheet   = client.open_by_key(SHEET_ID).sheet1

# ── Flask 앱 (헬스체크) ──
app = Flask(__name__)
@app.route("/health")
def health():
    return "OK", 200

# ── 체크리스트 항목 ──
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

# ── 알림 스케줄 ──
async def send_reminder(app):
    for uid in user_states:
        try:
            await app.bot.send_message(
                chat_id=uid,
                text="🕘 체크리스트 시간입니다! /start [종목명] 입력해주세요."
            )
        except:
            pass

def schedule_reminders(app):
    schedule.every().day.at("09:10").do(lambda: asyncio.create_task(send_reminder(app)))

# ── /start 핸들러 ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    stock = "미입력" if not context.args else " ".join(context.args)
    user_states[uid] = {
        'phase': 'checklist',
        'step': 0,
        'answers': [],
        'stock': stock
    }
    await update.message.reply_text(f"🧠 [{stock}] 체크리스트 시작\n{questions[0]}")

# ── 응답 핸들러 ──
async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text.strip()
    state = user_states.get(uid)
    if not state:
        return await update.message.reply_text("👉 먼저 /start [종목명] 입력해주세요.")

    # 1) 체크리스트 단계
    if state['phase'] == 'checklist':
        txt_up = txt.upper()
        if txt_up not in ['Y','N']:
            return await update.message.reply_text("Y 또는 N 으로 답해주세요.")
        state['answers'].append(txt_up)
        state['step'] += 1
        if state['step'] < len(questions):
            return await update.message.reply_text(questions[state['step']])

        # 체크리스트 완료 → 결과 계산
        yes = sum(1 for a in state['answers'] if a == 'Y')
        res = "✅ 진입 가능" if yes >= 7 else "❌ 진입 보류"
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        d_str = now.strftime("%Y-%m-%d"); t_str = now.strftime("%H:%M")
        state.update({
            'phase': 'post',
            'yes_count': yes,
            'result': res,
            'date': d_str,
            'time': t_str
        })
        return await update.message.reply_text(
            f"{res} ({yes}/10)\n"
            "이제 이번 매매의 👉 손익(퍼센트) 을 입력해주세요. 예: +5.3% 또는 -2%"
        )

    # 2) 손익(퍼센트) 입력 단계
    if state['phase'] == 'post' and 'pnl' not in state:
        txt_pct = txt
        if not txt_pct.endswith('%'):
            return await update.message.reply_text("퍼센트 단위로 입력해주세요. 예: +5.3% 또는 -2%")
        try:
            pct = float(txt_pct[:-1])
        except ValueError:
            return await update.message.reply_text("올바른 퍼센트 숫자를 입력해주세요. 예: +5.3% 또는 -2%")
        state['pnl'] = f"{pct:.2f}%"
        return await update.message.reply_text(
            "좋습니다! 이번 매매에서의 실수 유형을 선택해주세요.\n"
            "1. 수익매도 안함\n2. 충족 안됐는데 진입\n"
            "3. 손절선 미설정\n4. 물타기\n번호를 쉼표로 구분해 입력예: 1,3"
        )

    # 3) 실수유형 입력 단계
    if state['phase'] == 'post' and 'pnl' in state:
        choices = [c.strip() for c in txt.split(',')]
        valid   = {'1','2','3','4'}
        if any(c not in valid for c in choices):
            return await update.message.reply_text("1~4번만 쉼표로 구분해 입력해주세요. 예: 2,4")
        mistakes = ",".join(choices)
        # 최종 시트 기록
        row = [
            state['date'], state['time'], state['stock']
        ] + state['answers'] + [
            state['yes_count'], state['result'],
            state['pnl'], mistakes
        ]
        sheet.append_row(row)
        await update.message.reply_text(
            f"✅ 기록 완료!\n손익: {state['pnl']}, 실수유형: {mistakes}"
        )
        del user_states[uid]

# ── 봇 폴링 실행 함수 ──
def run_bot():
    import nest_asyncio
    nest_asyncio.apply()
    print("🟢 [지선 봇] Polling 스레드 시작")
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_response))
    print("🟢 [지선 봇] Telegram Polling 실행 중…")
    # 시그널 훅 무효화
    asyncio.run(app_bot.run_polling(stop_signals=None))

# ── 메인 ──
if __name__ == "__main__":
    # Flask + Telegram 폴링을 동시에 실행
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    schedule_reminders(app)   # 09:10 알림 설정
    app.run(host="0.0.0.0", port=10000)
