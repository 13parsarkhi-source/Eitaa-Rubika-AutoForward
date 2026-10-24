
import os
import time
import requests
from flask import Flask, jsonify

app = Flask(__name__)

TOKEN = os.environ.get("RUBIKA_BOT_TOKEN")
API = f"https://botapi.rubika.ir/v3/{TOKEN}"

def call_api(method, data=None):
    response = requests.post(
        f"{API}/{method}",
        json=data or {},
        timeout=25
    )
    response.raise_for_status()
    return response.json()

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
        "token_configured": bool(TOKEN)
    })

def run_bot():
    offset_id = None
    print("Rubika bot started")

    while True:
        try:
            payload = {"limit": 10}
            if offset_id:
                payload["offset_id"] = offset_id

            result = call_api("getUpdates", payload)
            data = result.get("data", result)
            updates = data.get("updates", [])

            for update in updates:
                chat_id = update.get("chat_id")
                message = update.get("new_message") or {}
                text = (message.get("text") or "").strip()

                if not chat_id:
                    continue
                if message.get("sender_type") == "Bot":
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
            print("Bot error:", error)
            time.sleep(5)

if __name__ == "__main__":
    import threading
    threading.Thread(target=run_bot, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
