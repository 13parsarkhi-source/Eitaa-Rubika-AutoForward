
import os
import time
import threading
import requests
from flask import Flask, jsonify

app = Flask(__name__)

TOKEN = os.environ.get("RUBIKA_BOT_TOKEN", "").strip()
API_URL = f"https://botapi.rubika.ir/v3/{TOKEN}"

session = requests.Session()
bot_thread_started = False
bot_lock = threading.Lock()


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
        raise RuntimeError(str(result))

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
    print("Rubika bot started", flush=True)

    offset_id = None

    while True:
        try:
            payload = {"limit": 10}

            if offset_id:
                payload["offset_id"] = offset_id

            result = call_api("getUpdates", payload)
            data = result.get("data") or result
            updates = data.get("updates") or []

            for update in updates:
                message = update.get("new_message") or {}
                chat_id = update.get("chat_id")
                text = (message.get("text") or "").strip()

                if not chat_id:
                    continue

                if text == "/start":
                    reply = (
                        "سلام! ربات فعال است ✅\n"
                        "برای راهنما /help را بفرست."
                    )
                elif text == "/help":
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

            offset_id = data.get("next_offset_id") or offset_id
            time.sleep(2)

        except Exception as error:
            print(
                f"Rubika bot error: {type(error).__name__}: {error}",
                flush=True
            )
            time.sleep(10)


def start_bot_thread():
    global bot_thread_started

    with bot_lock:
        if bot_thread_started:
            return

        thread = threading.Thread(
            target=run_bot,
            daemon=True,
            name="rubika-bot"
        )
        thread.start()


# Start the bot when the app is loaded by Gunicorn.
start_bot_thread()
