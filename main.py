
import os
import json
import time
import logging
import threading
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify
from eitaa import Eitaa

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("RUBIKA_BOT_TOKEN", "").strip()
TARGET_CHAT_ID = os.environ.get(
    "RUBIKA_TARGET_CHAT_ID", "@azmayeshys3"
).strip()

API_URL = f"https://botapi.rubika.ir/v3/{TOKEN}"
STATE_FILE = os.environ.get("STATE_FILE", "eitaa_state.json")
POLL_SECONDS = 15

session = requests.Session()
stop_event = threading.Event()
bot_thread = None
bot_lock = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
            if isinstance(state, dict):
                return state
    except (OSError, ValueError):
        pass

    return {}


def save_state(state):
    temp_file = STATE_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(temp_file, STATE_FILE)


def call_api(method, payload):
    if not TOKEN:
        raise RuntimeError("RUBIKA_BOT_TOKEN is missing")

    response = session.post(
        f"{API_URL}/{method}",
        json=payload,
        timeout=25,
    )
    response.raise_for_status()
    result = response.json()

    if not isinstance(result, dict):
        raise RuntimeError("Unexpected Rubika API response")

    if result.get("status") == "ERROR":
        raise RuntimeError(f"Rubika API rejected {method}")

    return result


def send_text(text):
    return call_api("sendMessage", {
        "chat_id": TARGET_CHAT_ID,
        "text": text,
    })


def get_latest_messages():
    messages = Eitaa.get_latest_messages("s3math56")

    if not isinstance(messages, list):
        raise RuntimeError("Unexpected Eitaa response")

    valid = []
    for message in messages:
        if not isinstance(message, dict):
            continue

        number = message.get("message_number")
        try:
            number = int(number)
        except (TypeError, ValueError):
            continue

        valid.append((number, message))

    return sorted(valid, key=lambda item: item[0])


def make_post_text(message, received_at):
    text = (message.get("text") or "").strip()
    image_link = (message.get("image_link") or "").strip()

    source_time = (
        message.get("iso_time")
        or message.get("time")
        or "در اطلاعات ایتا موجود نیست"
    )

    sent_at = now_iso()

    parts = [
        text or "این مطلب متن ندارد.",
        "",
        "📊 گزارش انتقال",
        f"زمان انتشار ایتا: {source_time}",
        f"زمان دریافت توسط ربات: {received_at}",
        f"زمان آماده‌سازی ارسال: {sent_at}",
    ]

    if image_link:
        parts.extend([
            "",
            "🖼 لینک تصویر مطلب:",
            image_link,
        ])

    parts.extend([
        "",
        "توجه: زمان آماده‌سازی با زمان قطعی رسیدن پیام یکسان نیست."
    ])

    return "\n".join(parts)


def run_forwarder():
    logging.info("Eitaa forwarder started")
    state = load_state()

    while not stop_event.is_set():
        try:
            messages = get_latest_messages()

            if not messages:
                time.sleep(POLL_SECONDS)
                continue

            latest_number = messages[-1][0]

            # در اجرای نخست، پست‌های موجود را فقط علامت‌گذاری می‌کنیم.
            if "last_message_number" not in state:
                state["last_message_number"] = latest_number
                save_state(state)
                logging.info(
                    "Initial baseline saved; old posts will not be sent"
                )
                time.sleep(POLL_SECONDS)
                continue

            last_number = int(state["last_message_number"])

            new_messages = [
                (number, msg)
                for number, msg in messages
                if number > last_number
            ]

            for number, message in new_messages:
                received_at = now_iso()
                outgoing_text = make_post_text(message, received_at)

                try:
                    send_text(outgoing_text)
                    logging.info(
                        "Forward request accepted for Eitaa post %s",
                        number,
                    )
                except Exception:
                    # عمداً دوباره ارسال نمی‌کنیم تا ریسک تکرار کمتر شود.
                    # این پست به‌عنوان ناموفق ثبت می‌شود.
                    logging.exception(
                        "Forward failed for Eitaa post %s; not retrying",
                        number,
                    )

                # هر پست فقط یک بار امتحان می‌شود؛ خطای ارسال را در گزارش
                # نگه می‌داریم تا خودکار باعث ارسال دوباره نشود.
                state["last_message_number"] = number
                state["last_attempt_at"] = now_iso()
                save_state(state)

            time.sleep(POLL_SECONDS)

        except Exception:
            logging.exception("Eitaa polling failed")
            time.sleep(POLL_SECONDS)


@app.route("/")
def home():
    return jsonify({
        "status": "running",
        "project": "Eitaa-Rubika-AutoForward",
    })


@app.route("/health")
def health():
    state = load_state()
    return jsonify({
        "ok": True,
        "token_configured": bool(TOKEN),
        "target_configured": bool(TARGET_CHAT_ID),
        "forwarder_started": (
            bot_thread is not None and bot_thread.is_alive()
        ),
        "last_message_number": state.get("last_message_number"),
    })


def start_forwarder():
    global bot_thread

    with bot_lock:
        if bot_thread is not None and bot_thread.is_alive():
            return

        bot_thread = threading.Thread(
            target=run_forwarder,
            daemon=True,
            name="eitaa-forwarder",
        )
        bot_thread.start()


start_forwarder()
