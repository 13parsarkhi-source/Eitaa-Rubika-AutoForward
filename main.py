
import os
import time
import json
import threading
import requests
from flask import Flask, jsonify
from eitaa import Eitaa

app = Flask(__name__)

TOKEN = os.environ.get("RUBIKA_BOT_TOKEN", "").strip()
API_URL = f"https://botapi.rubika.ir/v3/{TOKEN}"

session = requests.Session()
stop_event = threading.Event()
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

    if not isinstance(result, dict):
        raise RuntimeError("Invalid Rubika API response")

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


@app.route("/test-eitaa")
def test_eitaa():
    try:
        post = Eitaa.get_message("s3math56", 1503)
        return app.response_class(
            response=json.dumps(
                {"ok": True, "post": post},
                ensure_ascii=False,
                default=str
            ),
            status=200,
            mimetype="application/json"
        )
    except Exception as error:
        app.logger.exception("Eitaa test failed")
        return jsonify({
            "ok": False,
            "error": str(error)[:500]
        }), 502


@app.route("/test-latest")
def test_latest():
    try:
        messages = Eitaa.get_latest_messages("s3math56")

        if not isinstance(messages, list):
            return jsonify({
                "ok": False,
                "error": "Unexpected result type",
                "result_type": type(messages).__name__
            }), 502

        summary = []

        for message in messages:
            if not isinstance(message, dict):
                continue

            image_link = message.get("image_link") or ""

            summary.append({
                "message_number": message.get("message_number"),
                "text": message.get("text", ""),
                "has_image_link": bool(image_link),
                "image_link": image_link,
                "time": message.get("iso_time", message.get("time")),
            })

        return app.response_class(
            response=json.dumps({
                "ok": True,
                "count": len(summary),
                "messages": summary
            }, ensure_ascii=False, default=str),
            status=200,
            mimetype="application/json"
        )

    except Exception as error:
        app.logger.exception("Latest Eitaa test failed")
        return jsonify({
            "ok": False,
            "error": str(error)[:500]
        }), 502


def run_bot():
    global bot_thread_started
    bot_thread_started = True
    print("Rubika bot polling started", flush=True)

    offset_id = None
    initialized = False
    processed_ids = set()

    while not stop_event.is_set():
        try:
            payload = {"limit": 10}

            if offset_id:
                payload["offset_id"] = offset_id

            result = call_api("getUpdates", payload)
            data = result.get("data") or result
            updates = data.get("updates") or []
            next_offset = data.get("next_offset_id")

            if next_offset:
                offset_id = str(next_offset)

            if not initialized:
                initialized = True
                print(
                    f"Initial updates skipped: {len(updates)}",
                    flush=True
                )
                time.sleep(2)
                continue

            for update in updates:
                if not isinstance(update, dict):
                    continue

                if update.get("type") != "NewMessage":
                    continue

                message = update.get("new_message") or {}
                if not isinstance(message, dict):
                    continue

                chat_id = update.get("chat_id")
                message_id = message.get("message_id")
                text = (message.get("text") or "").strip()

                if not chat_id or not message_id:
                    continue

                key = f"{chat_id}:{message_id}"

                if key in processed_ids:
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

                processed_ids.add(key)

                call_api("sendMessage", {
                    "chat_id": str(chat_id),
                    "text": reply
                })

                print("Reply sent once", flush=True)

            if len(processed_ids) > 2000:
                processed_ids.clear()

            time.sleep(2)

        except Exception:
            app.logger.exception("Rubika polling error")
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


start_bot_thread()
