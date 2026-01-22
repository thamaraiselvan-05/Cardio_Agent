import os
import re
import requests
from flask import Blueprint, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, ConversationHandler
from dotenv import load_dotenv

load_dotenv()


# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
BACKEND_URL = os.getenv("BACKEND_URL")

if not BOT_TOKEN or not BACKEND_URL:
    raise ValueError("BOT_TOKEN or BACKEND_URL not set")

bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher(bot, None, workers=1, use_context=True)

telegram_webhook = Blueprint("telegram_webhook", __name__)

ADD_PATIENT_URL = f"{BACKEND_URL}/api/add-patient"
PREDICT_URL = f"{BACKEND_URL}/api/predict"


# ---------------- STATES ----------------
AGE, BP, CHOL, SUGAR, HR, LIFE, FAMILY = range(7)


# ---------------- UTILITIES ----------------
def extract_number(text):
    return int(text.strip()) if text.strip().isdigit() else None


def extract_systolic_bp(text):
    match = re.fullmatch(r"(\d{2,3})\s*/\s*\d{2,3}", text.strip())
    if match:
        return int(match.group(1))
    return extract_number(text)


# ---------------- START ----------------
def start(update, context):
    context.user_data.clear()
    update.message.reply_text(
        "🫀 *Welcome to CardioGuard AI*\n\n"
        "I’ll ask you *7 simple questions* to assess your heart health.\n"
        "👉 Please reply using numbers or the given options.\n\n"
        "*Question 1️⃣ – Age*\n"
        "Enter your age\n\n"
        "📝 *Example:* `22` or `45`",
        parse_mode="Markdown"
    )
    return AGE


# ---------------- AGE ----------------
def age(update, context):
    value = extract_number(update.message.text)
    if not value or value > 120:
        update.message.reply_text(
            "❌ Invalid age.\n\n"
            "Please enter age as a *number only*.\n"
            "📝 Example: `25`"
        )
        return AGE

    context.user_data["age"] = value
    update.message.reply_text(
        "*Question 2️⃣ – Blood Pressure*\n"
        "Enter your *blood pressure*.\n\n"
        "📝 Examples:\n"
        "• `120/80`\n"
        "• `130/85`\n"
        "• `120`\n\n"
        "ℹ️ Only the *top number (systolic)* is used.",
        parse_mode="Markdown"
    )
    return BP


# ---------------- BP ----------------
def bp(update, context):
    value = extract_systolic_bp(update.message.text)
    if not value:
        update.message.reply_text(
            "❌ Invalid blood pressure format.\n\n"
            "📝 Examples:\n"
            "• `120/80`\n"
            "• `130/85`\n"
            "• `120`",
            parse_mode="Markdown"
        )
        return BP

    context.user_data["blood_pressure"] = value
    update.message.reply_text(
        "*Question 3️⃣ – Cholesterol*\n"
        "Enter your cholesterol level (mg/dL).\n\n"
        "📝 Example: `180`",
        parse_mode="Markdown"
    )
    return CHOL


# ---------------- CHOLESTEROL ----------------
def chol(update, context):
    value = extract_number(update.message.text)
    if not value:
        update.message.reply_text(
            "❌ Invalid cholesterol value.\n\n"
            "📝 Example: `200`"
        )
        return CHOL

    context.user_data["cholesterol"] = value
    update.message.reply_text(
        "*Question 4️⃣ – Blood Sugar*\n"
        "Enter your *fasting blood sugar* (mg/dL).\n\n"
        "📝 Example: `90`",
        parse_mode="Markdown"
    )
    return SUGAR


# ---------------- BLOOD SUGAR ----------------
def sugar(update, context):
    value = extract_number(update.message.text)
    if not value:
        update.message.reply_text(
            "❌ Invalid blood sugar value.\n\n"
            "📝 Example: `100`"
        )
        return SUGAR

    context.user_data["blood_sugar"] = value
    update.message.reply_text(
        "*Question 5️⃣ – Heart Rate*\n"
        "Enter your *resting heart rate* (beats per minute).\n\n"
        "📝 Example: `72`",
        parse_mode="Markdown"
    )
    return HR


# ---------------- HEART RATE ----------------
def hr(update, context):
    value = extract_number(update.message.text)
    if not value:
        update.message.reply_text(
            "❌ Invalid heart rate.\n\n"
            "📝 Example: `75`"
        )
        return HR

    context.user_data["heart_rate"] = value
    update.message.reply_text(
        "*Question 6️⃣ – Physical Activity*\n"
        "Select your activity level.\n\n"
        "📝 Type one:\n"
        "• `sedentary` (little or no exercise)\n"
        "• `moderate` (3–5 days/week)\n"
        "• `active` (daily exercise)",
        parse_mode="Markdown"
    )
    return LIFE


# ---------------- LIFESTYLE ----------------
def life(update, context):
    value = update.message.text.lower()
    if value not in ["sedentary", "moderate", "active"]:
        update.message.reply_text(
            "❌ Invalid option.\n\n"
            "📝 Please type exactly:\n"
            "`sedentary`, `moderate`, or `active`"
        )
        return LIFE

    context.user_data["lifestyle"] = value
    update.message.reply_text(
        "*Question 7️⃣ – Family History*\n"
        "Do you have a *family history of heart disease*?\n\n"
        "📝 Reply with:\n"
        "• `yes`\n"
        "• `no`",
        parse_mode="Markdown"
    )
    return FAMILY


# ---------------- FINAL ----------------
def family(update, context):
    value = update.message.text.lower()
    if value not in ["yes", "no"]:
        update.message.reply_text(
            "❌ Invalid response.\n\n"
            "📝 Please reply with `yes` or `no`."
        )
        return FAMILY

    context.user_data["family_history"] = value
    context.user_data["result"] = 0

    # 1️⃣ Save patient data
    requests.post(ADD_PATIENT_URL, json=context.user_data, timeout=3)

    update.message.reply_text("⏳ *Analyzing your heart health...*", parse_mode="Markdown")

    # 2️⃣ Predict (numeric fields only)
    predict_payload = {
        "age": context.user_data["age"],
        "blood_pressure": context.user_data["blood_pressure"],
        "cholesterol": context.user_data["cholesterol"],
        "blood_sugar": context.user_data["blood_sugar"],
        "heart_rate": context.user_data["heart_rate"]
    }

    try:
        pred_resp = requests.post(PREDICT_URL, json=predict_payload, timeout=3)
        prediction = pred_resp.json()
    except Exception:
        update.message.reply_text("⚠️ Prediction service temporarily unavailable.")
        return ConversationHandler.END

    # 3️⃣ Final Result
    if prediction["risk"] == "HIGH":
        conclusion = (
            "🔴 *High Cardiac Risk*\n\n"
            "⚠️ Please consult a cardiologist.\n"
            "Adopt heart-healthy habits."
        )
    else:
        conclusion = (
            "🟢 *Low Cardiac Risk*\n\n"
            "✅ You’re doing well.\n"
            "Maintain a healthy lifestyle."
        )

    update.message.reply_text(
        f"🫀 *Heart Risk Assessment Result*\n\n"
        f"*Risk Level:* {prediction['risk']}\n"
        f"*Probability:* {prediction['probability']}\n\n"
        f"{conclusion}",
        parse_mode="Markdown"
    )

    context.user_data.clear()
    return ConversationHandler.END


# ---------------- HANDLER ----------------
conv = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        AGE: [MessageHandler(Filters.text & ~Filters.command, age)],
        BP: [MessageHandler(Filters.text & ~Filters.command, bp)],
        CHOL: [MessageHandler(Filters.text & ~Filters.command, chol)],
        SUGAR: [MessageHandler(Filters.text & ~Filters.command, sugar)],
        HR: [MessageHandler(Filters.text & ~Filters.command, hr)],
        LIFE: [MessageHandler(Filters.text & ~Filters.command, life)],
        FAMILY: [MessageHandler(Filters.text & ~Filters.command, family)],
    },
    fallbacks=[]
)

dispatcher.add_handler(conv)


# ---------------- WEBHOOK ----------------
@telegram_webhook.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "OK", 200
