import asyncio
import logging
import os
import sqlite3

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)

# =========================================================
# CONFIG / SOZLAMALAR
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "BOT_TOKENINGIZNI_SHUYERGA_YOZING")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5950184202"))  # Admin ID
CHANNEL_ID = os.getenv("CHANNEL_ID", "@kanal_username") # Otzyv kanalingiz username yoki IDsi

if not BOT_TOKEN or BOT_TOKEN == "BOT_TOKENINGIZNI_SHUYERGA_YOZING":
    logging.warning("⚠️ BOT_TOKEN o'rnatilmagan! Kod ichiga yoki Environment Variables'ga yozing.")

# =========================================================
# DATABASE SETUP
# =========================================================

conn = sqlite3.connect("openbudget_bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    phone TEXT,
    referrer_id INTEGER,
    balance INTEGER DEFAULT 0,
    is_banned INTEGER DEFAULT 0,
    advertising INTEGER DEFAULT 1
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    link TEXT NOT NULL,
    is_active INTEGER DEFAULT 1
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

default_settings = {
    "start_text": "Assalomu alaykum! 👋\n\n💠 OpenBudget botiga xush kelibsiz!\n\nKerakli bo'limni tanlang 👇",
    "start_photo": "",
    "no_project_text": "⏳ Hozircha ovoz berish boshlanmagan.",
    "warning_text": "⚠️ **OGOHLANTIRISH:** Qalbaki screenshotlar bloklanadi.",
    "warning_photo": "",
    "warning_photo_2": "",
    "referral_bonus": "1000",
    "vote_price": "5000",
    "min_withdraw": "20000"
}

for key, val in default_settings.items():
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))

conn.commit()

def get_setting(key):
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else ""

def set_setting(key, value):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()

# =========================================================
# BOT & DISPATCHER INITIALIZATION
# =========================================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# =========================================================
# FSM STATES
# =========================================================

class UserStates(StatesGroup):
    waiting_phone = State()
    waiting_screenshot = State()
    
    withdraw_amount = State()
    withdraw_requisite = State()
    withdraw_confirm = State()

class AdminStates(StatesGroup):
    project_title = State()
    project_link = State()

    broadcast_photo = State()
    broadcast_text = State()

    admin_proof_photo = State()
    admin_proof_text = State()

# =========================================================
# KEYBOARDS
# =========================================================

def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💠 Ovoz berish")],
            [KeyboardButton(text="💵 Balansim"), KeyboardButton(text="💳 Pul yechish")],
            [KeyboardButton(text="👥 Referal"), KeyboardButton(text="📊 Top 10")],
            [KeyboardButton(text="⚙️ Sozlamalar")]
        ],
        resize_keyboard=True
    )

def phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)],
            [KeyboardButton(text="⬅️ Orqaga")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Loyiha qo'shish"), KeyboardButton(text="🗑 Loyihalarni o'chirish")],
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Reklama yuborish")],
            [KeyboardButton(text="❌ Admin paneldan chiqish")]
        ],
        resize_keyboard=True
    )

def back_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Orqaga")]],
        resize_keyboard=True
    )

# =========================================================
# START & NAVIGATION
# =========================================================

@dp.message(CommandStart())
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)", (user_id,))
    conn.commit()

    start_text = get_setting("start_text")
    await message.answer(start_text, reply_markup=main_keyboard())

@dp.message(F.text == "⬅️ Orqaga")
async def back_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu.", reply_markup=main_keyboard())

# =========================================================
# BALANS & PUL YECHISH TIZIMI
# =========================================================

@dp.message(F.text == "💵 Balansim")
async def balance_handler(message: types.Message):
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
    row = cursor.fetchone()
    balance = row[0] if row else 0
    min_w = get_setting("min_withdraw")

    await message.answer(
        f"💰 **Balansingiz:** {balance:,} so'm\n"
        f"💳 **Minimal yechish summasi:** {int(min_w):,} so'm",
        parse_mode="Markdown"
    )

@dp.message(F.text == "💳 Pul yechish")
async def withdraw_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
    row = cursor.fetchone()
    balance = row[0] if row else 0
    min_w = int(get_setting("min_withdraw") or 20000)

    if balance < min_w:
        await message.answer(
            f"❌ **Mablag' yetarli emas!**\n\n"
            f"Sizning balansingiz: {balance:,} so'm\n"
            f"Minimal yechish summasi: {min_w:,} so'm",
            parse_mode="Markdown"
        )
        return

    await state.set_state(UserStates.withdraw_amount)
    await message.answer(
        f"💳 **Pul yechish bo'limi**\n\n"
        f"Sizning balansingiz: {balance:,} so'm\n"
        f"Minimal yechish summasi: {min_w:,} so'm\n\n"
        f"Necha pul yechmoqchisiz? Summani raqamda kiriting:",
        reply_markup=back_keyboard(),
        parse_mode="Markdown"
    )

@dp.message(UserStates.withdraw_amount)
async def withdraw_amount_step(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Asosiy menyu.", reply_markup=main_keyboard())
        return

    if not message.text.isdigit():
        await message.answer("❌ Iltimos, faqat raqam kiriting!")
        return

    amount = int(message.text)
    min_w = int(get_setting("min_withdraw") or 20000)

    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
    balance = cursor.fetchone()[0]

    if amount < min_w:
        await message.answer(f"❌ Minimal yechish summasi {min_w:,} so'm!")
        return

    if amount > balance:
        await message.answer(f"❌ Balansingizda yetarli mablag' yo'q! Balans: {balance:,} so'm")
        return

    await state.update_data(amount=amount)
    await state.set_state(UserStates.withdraw_requisite)
    await message.answer(
        "💳 Pul o'tkazilishi kerak bo'lgan **Karta raqami** (16 xonali) yoki **Telefon raqami**ni kiriting:",
        parse_mode="Markdown"
    )

@dp.message(UserStates.withdraw_requisite)
async def withdraw_req_step(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Asosiy menyu.", reply_markup=main_keyboard())
        return

    req = message.text.strip()
    data = await state.get_data()
    amount = data["amount"]

    await state.update_data(req=req)
    await state.set_state(UserStates.withdraw_confirm)

    confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, tasdiqlayman", callback_data="confirm_withdraw"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_withdraw")
        ]
    ])

    await message.answer(
        "❓ **Rostdan ham pulni yechib olmoqchimisiz?**\n\n"
        f"👤 **User ID:** `{message.from_user.id}`\n"
        f"💰 **Summa:** {amount:,} so'm\n"
        f"💳 **Karta / Raqam:** `{req}`",
        reply_markup=confirm_keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(UserStates.withdraw_confirm, F.data == "cancel_withdraw")
async def cancel_withdraw_cb(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Pul yechish so'rovi bekor qilindi.")
    await call.answer()

@dp.callback_query(UserStates.withdraw_confirm, F.data == "confirm_withdraw")
async def process_withdraw_cb(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount = data["amount"]
    req = data["req"]
    user_id = call.from_user.id

    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    balance = cursor.fetchone()[0]

    if balance < amount:
        await call.message.edit_text("❌ Balansingizda yetarli pul qolmadi.")
        await state.clear()
        return

    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

    admin_btn = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ To'lab berdim", callback_data=f"pay_ok_{user_id}_{amount}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pay_no_{user_id}_{amount}")
        ]
    ])

    admin_text = (
        "📥 **YANGI PUL YECHISH SO'ROVI**\n\n"
        f"👤 **User ID:** `{user_id}`\n"
        f"💰 **Summa:** {amount:,} so'm\n"
        f"💳 **Karta / Raqam:** `{req}`"
    )

    await bot.send_message(ADMIN_ID, admin_text, reply_markup=admin_btn, parse_mode="Markdown")
    await call.message.edit_text("✅ So'rovingiz adminga yuborildi! Tez orada pulingiz o'tkaziladi.")
    await state.clear()

# =========================================================
# ADMIN TO'LOV MANTIQI (ADMIN PROOF)
# =========================================================

@dp.callback_query(F.data.startswith("pay_no_"))
async def admin_reject_pay(call: types.CallbackQuery):
    _, _, target_id, amount = call.data.split("_")
    target_id, amount = int(target_id), int(amount)

    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_id))
    conn.commit()

    try:
        await bot.send_message(target_id, f"❌ Sizning {amount:,} so'mlik pul yechish so'rovingiz rad etildi va pul balansingizga qaytarildi.")
    except Exception:
        pass

    await call.message.edit_text(call.message.text + "\n\n❌ **RAD ETILDI (Pul qaytarildi)**")
    await call.answer("Rad etildi!")

@dp.callback_query(F.data.startswith("pay_ok_"))
async def admin_approve_pay_start(call: types.CallbackQuery, state: FSMContext):
    _, _, target_id, amount = call.data.split("_")

    await state.update_data(target_id=target_id, amount=amount)
    await state.set_state(AdminStates.admin_proof_photo)

    await bot.send_message(
        ADMIN_ID,
        f"📸 User `{target_id}` ga to'langanini tasdiqlovchi **Chek (Screenshot)** yuboring:",
        reply_markup=back_keyboard(),
        parse_mode="Markdown"
    )
    await call.answer()

@dp.message(AdminStates.admin_proof_photo, F.photo)
async def admin_proof_photo_step(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(proof_photo=photo_id)
    await state.set_state(AdminStates.admin_proof_text)
    await message.answer("✍️ Endi foydalanuvchiga yuboriladigan matnni kiriting (masalan: *Rahmat, ishonch uchun!*):")

@dp.message(AdminStates.admin_proof_text, F.text)
async def admin_proof_text_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_id = int(data["target_id"])
    amount = int(data["amount"])
    photo_id = data["proof_photo"]
    text_to_user = message.text

    try:
        await bot.send_photo(
            target_id,
            photo=photo_id,
            caption=f"🎉 **To'lovingiz muvaffaqiyatli amalga oshirildi!**\n\n💰 Summa: {amount:,} so'm\n💬 Admin xabari: {text_to_user}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Userga chek yuborishda xato: {e}")

    try:
        review_text = (
            "💳 **MUVAFFAQIYATLI TO'LOV!**\n\n"
            f"👤 **User ID:** `{target_id}`\n"
            f"💰 **Yechib olgan summasi:** {amount:,} so'm\n"
            "✅ To'lov bot tomonidan to'lab berildi."
        )
        await bot.send_photo(CHANNEL_ID, photo=photo_id, caption=review_text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Kanalga otzyv yuborishda xato: {e}")

    await state.clear()
    await message.answer("✅ To'lov cheki foydalanuvchiga va kanalga muvaffaqiyatli yuborildi!", reply_markup=admin_keyboard())

# =========================================================
# OVOZ BERISH
# =========================================================

@dp.message(F.text == "💠 Ovoz berish")
async def voting_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT id, title, link FROM projects WHERE is_active = 1 ORDER BY id DESC")
    projects = cursor.fetchall()

    if not projects:
        no_project_text = get_setting("no_project_text")
        await message.answer(no_project_text)
        return

    await state.set_state(UserStates.waiting_phone)
    await message.answer("📞 Telefon raqamingizni yuboring:", reply_markup=phone_keyboard())

@dp.message(UserStates.waiting_phone, F.contact)
async def phone_contact_handler(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number
    await save_phone_and_show_projects(message, phone, state)

@dp.message(UserStates.waiting_phone, F.text)
async def phone_text_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Asosiy menyu.", reply_markup=main_keyboard())
        return
    await save_phone_and_show_projects(message, message.text, state)

async def save_phone_and_show_projects(message, phone, state):
    cursor.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, message.from_user.id))
    conn.commit()

    cursor.execute("SELECT id, title, link FROM projects WHERE is_active = 1 ORDER BY id DESC")
    projects = cursor.fetchall()
    vote_price = get_setting("vote_price")

    text = f"📞 Raqam: {phone}\n💵 Har bir ovoz uchun: {int(vote_price):,} so'm\n\n"
    buttons = []
    for pid, title, link in projects:
        text += f"🎯 {title}\n"
        buttons.append([InlineKeyboardButton(text=f"🎯 {title}", url=link)])

    buttons.append([InlineKeyboardButton(text="📸 Screenshot yuborish", callback_data="send_screenshot")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "send_screenshot")
async def screenshot_start(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_screenshot)
    await call.message.answer("📸 Screenshotni rasm shaklida yuboring:")
    await call.answer()

@dp.message(UserStates.waiting_screenshot, F.photo)
async def receive_screenshot(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    cursor.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    phone = row[0] if (row and row[0]) else "Noma'lum"

    admin_buttons = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"reject_{user_id}")
        ]
    ])

    await bot.send_photo(
        ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=f"📸 **Yangi ovoz**\n👤 ID: `{user_id}`\n📞 Tel: `{phone}`",
        reply_markup=admin_buttons,
        parse_mode="Markdown"
    )

    await message.answer("✅ Screenshot adminga yuborildi.", reply_markup=main_keyboard())
    await state.clear()

@dp.callback_query(F.data.startswith("approve_"))
async def approve_vote(call: types.CallbackQuery):
    target_user_id = int(call.data.split("_")[1])
    vote_price = int(get_setting("vote_price") or 5000)

    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (vote_price, target_user_id))
    conn.commit()

    try:
        await bot.send_message(target_user_id, f"🎉 Ovoz tasdiqlandi! Balansingizga +{vote_price:,} so'm qo'shildi.")
    except Exception:
        pass

    await call.message.edit_caption(caption=call.message.caption + "\n\n✅ TASDIQLANDI")
    await call.answer("Tasdiqlandi!")

@dp.callback_query(F.data.startswith("reject_"))
async def reject_vote(call: types.CallbackQuery):
    target_user_id = int(call.data.split("_")[1])
    try:
        await bot.send_message(target_user_id, "❌ Screenshotingiz rad etildi.")
    except Exception:
        pass
    await call.message.edit_caption(caption=call.message.caption + "\n\n❌ RAD ETILDI")
    await call.answer("Rad etildi!")

# =========================================================
# OTHER FEATURES (REFERRAL, TOP 10, ADMIN PANEL)
# =========================================================

@dp.message(F.text == "👥 Referal")
async def referral_handler(message: types.Message):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={message.from_user.id}"
    cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (message.from_user.id,))
    count = cursor.fetchone()[0]
    ref_bonus = get_setting("referral_bonus")

    await message.answer(
        "👥 **Referal tizimi**\n\n"
        f"🔗 Havolangiz:\n`{link}`\n\n"
        f"👤 Taklif qilganlaringiz: {count} ta\n"
        f"💵 Har bir taklif uchun: {int(ref_bonus):,} so'm",
        parse_mode="Markdown"
    )

@dp.message(F.text == "📊 Top 10")
async def top_users(message: types.Message):
    cursor.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    rows = cursor.fetchall()
    text = "🏆 **TOP 10 FOYDALANUVCHILAR**\n\n"
    for index, (uid, balance) in enumerate(rows, 1):
        text += f"{index}. `{uid}` — {balance:,} so'm\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("admin"))
async def admin_command(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 ADMIN PANEL", reply_markup=admin_keyboard())

@dp.message(F.text == "❌ Admin paneldan chiqish")
async def admin_exit(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Asosiy menyu.", reply_markup=main_keyboard())

# =========================================================
# RUN BOT
# =========================================================

async def main():
    logging.info("OpenBudget bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
