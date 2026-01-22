from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, render_template_string
import psycopg2
import pandas as pd
import joblib
import os

from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from bot_webhook import telegram_webhook

app = Flask(__name__)
app.register_blueprint(telegram_webhook)

# ---------------- DATABASE CONFIG ----------------
DATABASE_URL = os.environ.get("DATABASE_URL")
MODEL_PATH = "heart_model.pkl"
print("DATABASE_URL =", os.environ.get("DATABASE_URL"))

# ---------------- DB CONNECTION ----------------
def get_db_connection():
    return psycopg2.connect(DATABASE_URL,sslmode="require")

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

# ---------------- TRAIN ML MODEL ----------------
def train_model():
    conn = get_db_connection()

    query = """
        SELECT age, blood_pressure, cholesterol,
               blood_sugar, heart_rate, result
        FROM patients
    """
    df = pd.read_sql(query, conn)
    conn.close()

    if len(df) < 5:
        print("⚠️ Not enough data to train ML model")
        return None

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

# ---------------- LOAD MODEL AT STARTUP ----------------
model = None

if os.path.exists(MODEL_PATH):
    model = joblib.load(MODEL_PATH)
    print("✅ ML model loaded")
else:
    print("⚠️ Model not found, will train on first prediction")


# ---------------- HOME PAGE (HTML + BOT LINK) ----------------
@app.route("/")
def home():
    bot_username = "CardioGaurdAi_bot"  # exact bot username
    bot_link = f"https://t.me/@CardioGaurdAi_bot"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=https://t.me/CardioGaurdAi_bot"

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>CardioGuard AI</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background: #f4f6f8;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
            }
            .card {
                background: white;
                padding: 40px;
                border-radius: 12px;
                text-align: center;
                box-shadow: 0 6px 15px rgba(0,0,0,0.1);
                max-width: 480px;
            }
            h1 {
                color: #d32f2f;
            }
            p {
                font-size: 16px;
                color: #333;
            }
            .btn {
                display: inline-block;
                margin-top: 20px;
                padding: 12px 25px;
                background: #0088cc;
                color: white;
                text-decoration: none;
                border-radius: 6px;
                font-size: 16px;
            }
            .btn:hover {
                background: #006fa3;
            }
            img {
                margin-top: 15px;
                border-radius: 8px;
            }
            .footer {
                margin-top: 20px;
                font-size: 13px;
                color: gray;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>❤️ CardioGuard AI</h1>
            <p>An AI-powered heart risk assessment system</p>

            <p><strong>Chat with our Telegram Bot</strong></p>
            <p>@{{ bot_username }}</p>

            <img src="{{ qr_url }}" alt="Telegram Bot QR Code">

            <br>
            <a class="btn" href="{{ bot_link }}" target="_blank">
                Start Telegram Bot
            </a>

            <div class="footer">
                Backend & ML running successfully 🚀
            </div>
        </div>
    </body>
    </html>
    """, bot_username=bot_username, bot_link=bot_link, qr_url=qr_url)


# ---------------- TEST DB ----------------
@app.route("/test-db")
def test_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM patients;")
    count = cur.fetchone()[0]
    conn.close()
    return jsonify({"patients_count": count})

# ---------------- ADD PATIENT ----------------
@app.route("/api/add-patient", methods=["POST"])
def add_patient():
    data = request.json

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO patients (
            age, blood_pressure, cholesterol, blood_sugar,
            heart_rate, lifestyle, family_history, result
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        data["age"],
        data["blood_pressure"],
        data["cholesterol"],
        data["blood_sugar"],
        data["heart_rate"],
        data["lifestyle"],
        data["family_history"],
        data["result"]
    ))

    conn.commit()
    conn.close()

    return jsonify({"message": "Patient data added successfully"})

# ---------------- ML PREDICTION ----------------
@app.route("/api/predict", methods=["POST"])
def predict():
    global model

    if model is None:
        model = train_model()

    data = request.json

    features = [[
        data["age"],
        data["blood_pressure"],
        data["cholesterol"],
        data["blood_sugar"],
        data["heart_rate"]
    ]]

    prediction = model.predict(features)[0]
    probability = model.predict_proba(features)[0][1]

    return jsonify({
        "risk": "HIGH" if prediction == 1 else "LOW",
        "probability": round(probability, 2)
    })

# ---------------- START APP ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
