import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({
        "status": "running",
        "project": "Eitaa-Rubika-AutoForward",
        "message": "Bot server is running!"
    })

@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "rubika_token_configured": bool(
            os.environ.get("RUBIKA_BOT_TOKEN")
        )
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
