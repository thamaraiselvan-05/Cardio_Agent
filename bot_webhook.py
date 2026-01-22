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

AGE, BP, CHOL, SUGAR, HR, LIFE, FAMILY = range(7)

# ---------------- UTILITIES ----------------
def extract_number(text):
    text = text.strip()
    return int(text) if text.isdigit() else None

def extract_systolic_bp(text):
    text = text.strip()
    match = re.fullmatch(r"(\d{2,3})\s*/\s*\d{2,3}", text)
    if match:
        return int(match.group(1))
    return int(text) if text.isdigit() else None

# ---------------- START ----------------
def start(update, context):
    context.user_data.clear()
    update.message.reply_text(
        "🫀 *Welcome to CardioGuard AI*\n\n"
        "Please enter your age (example: 22):",
        parse_mode="Markdown"
    )
    return AGE

# ---------------- AGE ----------------
def age(update, context):
    value = extract_number(update.message.text)
    if value is None or value < 1 or value > 120:
        update.message.reply_text("❌ Please enter a valid age.")
        return AGE

    context.user_data["age"] = value
    update.message.reply_text(
        "Enter your blood pressure (example: 120/80 or 120).\n"
        "⚠️ Only systolic value will be used."
    )
    return BP

# ---------------- BP ----------------
def bp(update, context):
    value = extract_systolic_bp(update.message.text)
    if value is None:
        update.message.reply_text("❌ Invalid BP format.")
        return BP

    context.user_data["blood_pressure"] = value
    update.message.reply_text("Enter cholesterol level:")
    return CHOL

# ---------------- CHOL ----------------
def chol(update, context):
    value = extract_number(update.message.text)
    if value is None:
        update.message.reply_text("❌ Enter numbers only.")
        return CHOL

    context.user_data["cholesterol"] = value
    update.message.reply_text("Enter blood sugar:")
    return SUGAR

# ---------------- SUGAR ----------------
def sugar(update, context):
    value = extract_number(update.message.text)
    if value is None:
        update.message.reply_text("❌ Enter numbers only.")
        return SUGAR

    context.user_data["blood_sugar"] = value
    update.message.reply_text("Enter heart rate:")
    return HR

# ---------------- HR ----------------
def hr(update, context):
    value = extract_number(update.message.text)
    if value is None:
        update.message.reply_text("❌ Enter numbers only.")
        return HR

    context.user_data["heart_rate"] = value
    update.message.reply_text("Lifestyle? (sedentary / moderate / active)")
    return LIFE

# ---------------- LIFE ----------------
def life(update, context):
    value = update.message.text.lower()
    if value not in ["sedentary", "moderate", "active"]:
        update.message.reply_text("❌ Type sedentary, moderate or active.")
        return LIFE

    context.user_data["lifestyle"] = value
    update.message.reply_text("Family history of heart disease? (yes / no)")
    return FAMILY

# ---------------- FINAL ----------------
def family(update, context):
    value = update.message.text.lower()
    if value not in ["yes", "no"]:
        update.message.reply_text("❌ Reply yes or no.")
        return FAMILY

    context.user_data["family_history"] = value
    context.user_data["result"] = 0

    # Save data
    requests.post(ADD_PATIENT_URL, json=context.user_data)

    # Predict
    prediction = requests.post(PREDICT_URL, json=context.user_data).json()

    # Conclusion
    if prediction["risk"] == "HIGH":
        conclusion = (
            "🔴 *High Cardiac Risk Detected*\n\n"
            "⚠️ You may require cardiac health support.\n"
            "Please consult a cardiologist as soon as possible."
        )
    else:
        conclusion = (
            "🟢 *Low Cardiac Risk*\n\n"
            "✅ You are doing fine.\n"
            "Maintain a healthy lifestyle."
        )

    update.message.reply_text(
        f"🫀 *Heart Risk Assessment*\n\n"
        f"Risk: *{prediction['risk']}*\n"
        f"Probability: *{prediction['probability']}*\n\n"
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
