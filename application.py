from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, render_template_string
import psycopg2
import pandas as pd
import joblib
import os
import traceback

from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

from bot_webhook import telegram_webhook


# ---------------- APP INIT ----------------
app = Flask(__name__)
app.register_blueprint(telegram_webhook)


# ---------------- CONFIG ----------------
DATABASE_URL = os.environ.get("DATABASE_URL")
MODEL_PATH = "heart_model.pkl"


# ---------------- DB CONNECTION ----------------
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def ensure_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id SERIAL PRIMARY KEY,
            age INT,
            blood_pressure INT,
            cholesterol INT,
            blood_sugar INT,
            heart_rate INT,
            lifestyle TEXT,
            family_history TEXT,
            result INT
        );
    """)
    conn.commit()
    conn.close()


ensure_table()

# ---------------- TEST DB CONNECTION ----------------
@app.route("/test-db")
def test_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM patients;")
        count = cur.fetchone()[0]
        conn.close()

        return {
            "status": "connected",
            "patients_count": count
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }, 500

# ---------------- FALLBACK MODEL ----------------
def create_default_model():
    """
    Safe fallback model to avoid prediction failures
    """
    model = LogisticRegression(max_iter=1000)
    X = [
        [30, 120, 180, 90, 70],
        [45, 140, 220, 110, 85],
        [60, 160, 260, 140, 95]
    ]
    y = [0, 1, 1]
    model.fit(X, y)
    return model


# ---------------- TRAIN MODEL ----------------
def train_model():
    conn = get_db_connection()
    query = """
        SELECT age, blood_pressure, cholesterol,
               blood_sugar, heart_rate, result
        FROM patients
    """
    df = pd.read_sql(query, conn)
    conn.close()

    # 🛟 Safety: Not enough data
    if len(df) < 5:
        print("⚠️ Not enough data — using fallback ML model")
        model = create_default_model()
        joblib.dump(model, MODEL_PATH)
        return model

    X = df.drop("result", axis=1)
    y = df["result"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = LogisticRegression(max_iter=1000)
    model.fit(X_train, y_train)

    acc = accuracy_score(y_test, model.predict(X_test))
    print(f"✅ ML Model trained | Accuracy: {acc:.2f}")

    joblib.dump(model, MODEL_PATH)
    return model


# ---------------- LOAD MODEL ----------------
print("🔄 Loading ML model...")

if os.path.exists(MODEL_PATH):
    model = joblib.load(MODEL_PATH)
    print("✅ ML model loaded from disk")
else:
    model = train_model()
    print("✅ ML model trained & ready")


# ---------------- HOME PAGE ----------------
@app.route("/")
def home():
    bot_username = "CardioGaurdAi_bot"
    bot_link = f"https://t.me/{bot_username}"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={bot_link}"

    return render_template_string("""
    <html>
    <head>
        <title>CardioGuard AI</title>
        <style>
            body {
                font-family: Arial;
                background: linear-gradient(135deg, #ffebee, #e3f2fd);
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
            }
            .card {
                background: white;
                padding: 40px;
                border-radius: 16px;
                text-align: center;
                box-shadow: 0 10px 30px rgba(0,0,0,0.15);
                max-width: 480px;
            }
            h1 { color: #d32f2f; }
            .btn {
                background: #0088cc;
                color: white;
                padding: 12px 25px;
                border-radius: 8px;
                text-decoration: none;
                display: inline-block;
                margin-top: 20px;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>❤️ CardioGuard AI</h1>
            <p>AI-powered heart risk assessment</p>
            <p><strong>@{{ bot_username }}</strong></p>
            <img src="{{ qr_url }}">
            <br>
            <a class="btn" href="{{ bot_link }}" target="_blank">Start Telegram Bot</a>
            <p style="margin-top:15px;font-size:13px;color:gray;">
                Backend + ML running smoothly 🚀
            </p>
        </div>
    </body>
    </html>
    """, bot_username=bot_username, bot_link=bot_link, qr_url=qr_url)


# ---------------- PREDICTION API ----------------
@app.route("/api/predict", methods=["POST"])
def predict():
    try:
        data = request.json

        features = [[
            int(data["age"]),
            int(data["blood_pressure"]),
            int(data["cholesterol"]),
            int(data["blood_sugar"]),
            int(data["heart_rate"])
        ]]

        prediction = model.predict(features)[0]
        probability = model.predict_proba(features)[0][1]

        return jsonify({
            "risk": "HIGH" if prediction == 1 else "LOW",
            "probability": round(float(probability), 2)
        })

    except Exception as e:
        print("❌ Prediction error:", e)
        traceback.print_exc()
        return jsonify({"error": "Prediction failed"}), 500


# ---------------- START APP ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
