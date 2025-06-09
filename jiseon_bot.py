import os
import json
from datetime import datetime, date
from zoneinfo import ZoneInfo
from collections import defaultdict
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ── 환경변수 로드 ──
BOT_TOKEN   = os.environ["BOT_TOKEN"]
SHEET_ID    = os.environ["SHEET_ID"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]
creds_dict  = json.loads(os.environ["GOOGLE_JSON"])

# ── Google Sheets 연결 ──
scope  = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
creds  = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gc     = gspread.authorize(creds)
sheet  = gc.open_by_key(SHEET_ID).sheet1

# ── 체크리스트 질문 ──
questions = [
    "1. 지금 충동적으로 진입하려는 것이 아니라고 확신할 수 있나요? (Y/N)",
    "2. '놓치면 안 된다'는 불안감 없이 매매하고 있나요? (Y/N)",
    "3. 직전 거래의 손익에 흔들리지 않고 있는 상태인가요? (Y/N)",
    "4. 오늘 감정 상태(피로, 과음, 스트레스 등)가 매매에 방해되지 않나요? (Y/N)",
    "5. 수익 모델에 따라 매매하고 있다는 자신이 있나요? (Y/N)",
    "6. 장 시작 10분은 지났나요? (Y/N)",
    "7. 갭이 8% 이하에서 출발했나요? (Y/N)",
    "8. 테마군 상승 또는 분당 100억 이상의 거래대금 발생 종목인가요? (Y/N)",
    "9. 일봉상 신고가 또는 박스권 돌파인가요? (Y/N)",
    "10. 돌파 시작 3분 이내 10% 이상 급등한 종목은 아닌가요? (Y/N)",
    "11. 1분봉 상 25억 이상의 거래대금이 2번 이상 발생했나요? (Y/N)",
    "12. 1분봉 상 박스권을 만들었나요? (Y/N)",
    "13. 1분봉 상 4개의 봉이 만들어졌나요? (Y/N)",
    "14. 1분봉 상 급등/급락을 반복하지 않나요? (Y/N)",
    "15. 단기 전고점 대비 -4.5% 이상 하락하지 않았나요? (Y/N)",
    "16. 좋은 뉴스가 발생했나요? (Y/N)"
]

user_states = {}
daily_entry_counts = {}  # user_id -> {"last_date": "YYYY-MM-DD", "count": 0}

# ── /start 핸들러 ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    stock = "미입력" if not context.args else " ".join(context.args)
    today = date.today().isoformat()

    user_data = daily_entry_counts.get(uid, {"last_date": "", "count": 0})

    if user_data["last_date"] != today:
        user_data = {"last_date": today, "count": 0}  # 날짜가 바뀌면 초기화

    if user_data["count"] >= 3:
        return await update.message.reply_text("⚠️ 오늘은 매매 3회를 모두 사용했습니다.\n내일 다시 체크리스트를 이용해 주세요.")

    
    user_states[uid] = {
        "phase": "checklist",
        "step": 0,
        "answers": [],
        "stock": stock,
    }

    count_str = f"(오늘 {user_data['count']}번째 매매)"
    await update.message.reply_text(f"🧠 [{stock}] 체크리스트 시작 {count_str}\n{questions[0]}")

# ── 응답 처리 핸들러 ──
async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()
    state = user_states.get(uid)
    if not state:
        return await update.message.reply_text("👉 먼저 /start [종목명] 으로 시작해주세요.")

    if state["phase"] == "checklist":
        t = text.upper()
        if t not in ("Y", "N"):
            return await update.message.reply_text("Y 또는 N 으로 답해주세요.")
        state["answers"].append(t)
        state["step"] += 1

        if state["step"] < len(questions):
            return await update.message.reply_text(questions[state["step"]])

        yes = sum(1 for a in state["answers"] if a == "Y")
        res = "✅ 진입 가능" if yes >= 12 else "❌ 진입 보류"
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        state.update({
            "phase": "post",
            "yes_count": yes,
            "result": res,
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"),
        })
        return await update.message.reply_text(
            f"{res} ({yes}/{len(questions)})\n이번 매매의 👉 손익(퍼센트) 을 입력해주세요. 예: +5.3% 또는 -2%"
        )

    if state["phase"] == "post" and "pnl" not in state:
        if not text.endswith("%"):
            return await update.message.reply_text("퍼센트로 입력해주세요. 예: +5.3% 또는 -2%")
        try:
            pct = float(text[:-1])
        except ValueError:
            return await update.message.reply_text("올바른 숫자를 입력해주세요.")
        state["pnl"] = f"{pct:.2f}%"
        return await update.message.reply_text(
            "이번 매매에서의 실수 유형을 선택해주세요:\n"
            "1. 수익매도 안함\n2. 충족 안됐는데 진입\n"
            "3. 손절선 미설정\n4. 물타기\n5. 홀딩시간 늘어남\n6. 없음\n"
            "예: 1,3 또는 6"
        )

    if state["phase"] == "post" and "pnl" in state:
        choices = [c.strip() for c in text.split(",")]
        if not all(c in ("1", "2", "3", "4", "5", "6") for c in choices):
            return await update.message.reply_text("1~6번 중에서 쉼표로 구분해 입력해주세요.")
        mistakes = ",".join(choices)

        row = [
            state["date"], state["time"], state["stock"],
            *state["answers"],
            state["yes_count"], state["result"],
            state["pnl"], mistakes,
        ]
        sheet.append_row(row)
        await update.message.reply_text(f"✅ 기록 완료!\n손익: {state['pnl']}, 실수: {mistakes}")
                # 체크리스트 완료로 간주하고 매매 횟수 카운트
        user_data = daily_entry_counts.get(uid, {"last_date": date.today().isoformat(), "count": 0})
        user_data["count"] += 1
        daily_entry_counts[uid] = user_data

        del user_states[uid]

# ── 애플리케이션 빌드 ──
application = (
    ApplicationBuilder()
    .token(BOT_TOKEN)
    .build()
)

application.add_handler(CommandHandler("start", start))
application.add_handler(
    MessageHandler(filters.TEXT & (~filters.COMMAND), handle_response)
)

if __name__ == "__main__":
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", "10000")),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )
