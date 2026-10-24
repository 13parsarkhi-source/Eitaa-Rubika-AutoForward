
import os
import time
import threading
from collections import deque

import requests
from flask import Flask, jsonify

app = Flask(__name__)

TOKEN = os.environ.get("RUBIKA_BOT_TOKEN", "").strip()
API_URL = f"https://botapi.rubika.ir/v3/{TOKEN}"

session = requests.Session()

bot_thread_started = False
bot_lock = threading.Lock()

# جلوگیری از پاسخ دادن چندباره به یک پیام
seen_ids = set()
seen_order = deque(maxlen=1000)


def remember_message(key):
    if key in seen_ids:
        return False

    if len(seen_order) == seen_order.maxlen:
        old_key = seen_order.popleft()
        seen_ids.discard(old_key)

    seen_order.append(key)
    seen_ids.add(key)
    return True


def call_api(method, payload=None):
    if not TOKEN:
        raise RuntimeError("RUBIKA_BOT_TOKEN is not configured")

    response = session.post(
        f"{API_URL}/{method}",
        json=payload or {},
        timeout=30
    )
    response.raise_for_status()

    result = response.json()

    if result.get("status") == "ERROR":
        raise RuntimeError(f"Rubika API error in {method}")

    return result


@app.route("/")
def home():
    return jsonify({
        "status": "running",
        "project": "Eitaa-Rubika-AutoForward"
    })


@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "token_configured": bool(TOKEN),
        "bot_thread_started": bot_thread_started
    })


def run_bot():
    global bot_thread_started
    bot_thread_started = True

    print("Rubika bot polling started", flush=True)
    offset_id = None

    while True:
        try:
            payload = {"limit": 10}

            if offset_id:
                payload["offset_id"] = offset_id

            result = call_api("getUpdates", payload)
            data = result.get("data") or result
            updates = data.get("updates") or []

            # قبل از پردازش پیام‌ها، موقعیت بعدی را ثبت کن
            next_offset = data.get("next_offset_id")
            if next_offset:
                offset_id = next_offset

            for update in updates:
                update_type = update.get("type")

                # فقط پیام جدید؛ رویدادهای دیگر نادیده گرفته می‌شوند
                if update_type and update_type != "NewMessage":
                    continue

                message = update.get("new_message") or {}
                chat_id = update.get("chat_id")
                message_id = message.get("message_id")
                message_text = (message.get("text") or "").strip()

                if not chat_id or not message_id:
                    continue

                unique_key = f"{chat_id}:{message_id}"

                if not remember_message(unique_key):
                    print("Duplicate message skipped", flush=True)
                    continue

                if message_text == "/start":
                    reply = (
                        "سلام! ربات فعال است ✅\n"
                        "برای راهنما /help را بفرست."
                    )
                elif message_text == "/help":
                    reply = (
                        "راهنمای ربات:\n"
                        "/start - شروع\n"
                        "/help - راهنما"
                    )
                else:
                    continue

                call_api("sendMessage", {
                    "chat_id": str(chat_id),
                    "text": reply
                })

                print(
                    f"Reply sent for message {message_id}",
                    flush=True
                )

            if updates and not next_offset:
                print(
                    "Warning: API did not return next_offset_id",
                    flush=True
                )

            time.sleep(2)

        except Exception as error:
            # توکن و متن خصوصی پیام‌ها را در گزارش چاپ نمی‌کنیم
            print(
                f"Polling error: {type(error).__name__}: {error}",
                flush=True
            )
            time.sleep(10)


def start_bot_thread():
    with bot_lock:
        if bot_thread_started:
            return

        thread = threading.Thread(
            target=run_bot,
            daemon=True,
            name="rubika-bot"
        )
        thread.start()


start_bot_thread()
