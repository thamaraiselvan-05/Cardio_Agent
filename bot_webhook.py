import os
import re
import requests
from flask import Blueprint, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, ConversationHandler
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BACKEND_URL = os.getenv("BACKEND_URL")

bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher(bot, None, workers=1, use_context=True)

telegram_webhook = Blueprint("telegram_webhook", __name__)

ADD_PATIENT_URL = f"{BACKEND_URL}/api/add-patient"
PREDICT_URL = f"{BACKEND_URL}/api/predict"

AGE, BP, CHOL, SUGAR, HR, LIFE, FAMILY = range(7)

# ---------------- UTILITY FUNCTIONS ----------------
def extract_number(text):
    return int(text) if text.isdigit() else None

def extract_systolic_bp(text):
    match = re.fullmatch(r"(\d{2,3})\s*/\s*\d{2,3}", text)
    if match:
        return int(match.group(1))
    return int(text) if text.isdigit() else None

# ---------------- BOT HANDLERS ----------------
def start(update, context):
    context.user_data.clear()
    update.message.reply_text("🫀 Welcome to CardioGuard AI\n\nEnter your age:")
    return AGE

def age(update, context):
    val = extract_number(update.message.text)
    if not val:
        update.message.reply_text("Enter valid age")
        return AGE
    context.user_data["age"] = val
    update.message.reply_text("Enter BP (120/80 or 120):")
    return BP

def bp(update, context):
    val = extract_systolic_bp(update.message.text)
    if not val:
        update.message.reply_text("Invalid BP")
        return BP
    context.user_data["blood_pressure"] = val
    update.message.reply_text("Enter cholesterol:")
    return CHOL

def chol(update, context):
    context.user_data["cholesterol"] = extract_number(update.message.text)
    update.message.reply_text("Enter blood sugar:")
    return SUGAR

def sugar(update, context):
    context.user_data["blood_sugar"] = extract_number(update.message.text)
    update.message.reply_text("Enter heart rate:")
    return HR

def hr(update, context):
    context.user_data["heart_rate"] = extract_number(update.message.text)
    update.message.reply_text("Lifestyle (sedentary/moderate/active):")
    return LIFE

def life(update, context):
    context.user_data["lifestyle"] = update.message.text.lower()
    update.message.reply_text("Family history? (yes/no)")
    return FAMILY

def family(update, context):
    context.user_data["family_history"] = update.message.text.lower()
    context.user_data["result"] = 0

    requests.post(ADD_PATIENT_URL, json=context.user_data)
    pred = requests.post(PREDICT_URL, json=context.user_data).json()

    update.message.reply_text(
        f"🫀 Risk: {pred['risk']}\nProbability: {pred['probability']}"
    )

    context.user_data.clear()
    return ConversationHandler.END

conv = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        AGE: [MessageHandler(Filters.text, age)],
        BP: [MessageHandler(Filters.text, bp)],
        CHOL: [MessageHandler(Filters.text, chol)],
        SUGAR: [MessageHandler(Filters.text, sugar)],
        HR: [MessageHandler(Filters.text, hr)],
        LIFE: [MessageHandler(Filters.text, life)],
        FAMILY: [MessageHandler(Filters.text, family)],
    },
    fallbacks=[]
)

dispatcher.add_handler(conv)

# ---------------- WEBHOOK ENDPOINT ----------------
@telegram_webhook.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "OK", 200
