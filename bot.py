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
)

# =========================================================
# CONFIG / SOZLAMALAR
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "BOT_TOKENINGIZNI_SHUYERGA_YOZING")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5950184202"))  # Admin ID
CHANNEL_ID = os.getenv("CHANNEL_ID", "@kanal_username")  # Otzyv kanali

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

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
    is_banned INTEGER DEFAULT 0
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
    "start_text": "Assalomu alaykum! 👋\n\n💠 OpenBudget botiga xush kelibsiz!\n\nOvoz berib pul ishlang!",
    "no_project_text": "⏳ Hozircha ovoz berish uchun faol loyihalar yo'q.",
    "warning_text": "⚠️ Fake screenshotlar uchun botdan bloklanasiz!",
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
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()

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
    # Loyiha qo'shish
    project_title = State()
    project_link = State()

    # Sozlamalar o'zgartirish
    set_start_text = State()
    set_vote_price = State()
    set_ref_bonus = State()
    set_min_withdraw = State()
    
    # Reklama
    broadcast_msg = State()

    # To'lov tasdiqlash
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
            [KeyboardButton(text="ℹ️ Yo'riqnoma")]
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
            [KeyboardButton(text="⚙️ Bot Sozlamalari"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="📢 Reklama yuborish"), KeyboardButton(text="❌ Admin paneldan chiqish")]
        ],
        resize_keyboard=True
    )

def settings_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Start matni"), KeyboardButton(text="💵 Ovoz narxi")],
            [KeyboardButton(text="👥 Referal bonusi"), KeyboardButton(text="💳 Min yechish summasi")],
            [KeyboardButton(text="⬅️ Admin panel")]
        ],
        resize_keyboard=True
    )

def back_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Orqaga")]],
        resize_keyboard=True
    )

# =========================================================
# START & REFERRAL SYSTEM
# =========================================================

@dp.message(CommandStart())
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    args = message.text.split()

    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user_exists = cursor.fetchone()

    if not user_exists:
        referrer_id = None
        if len(args) > 1 and args[1].isdigit():
            ref_candidate = int(args[1])
            if ref_candidate != user_id:
                referrer_id = ref_candidate

        cursor.execute("INSERT INTO users (user_id, referrer_id, balance) VALUES (?, ?, 0)", (user_id, referrer_id))
        conn.commit()

        if referrer_id:
            ref_bonus = int(get_setting("referral_bonus") or 1000)
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (ref_bonus, referrer_id))
            conn.commit()
            try:
                await bot.send_message(referrer_id, f"🎉 Siz taklif qilgan foydalanuvchi botga kirdi! Balansingizga +{ref_bonus:,} so'm qo'shildi.")
            except Exception:
                pass

    start_text = get_setting("start_text")
    await message.answer(start_text, reply_markup=main_keyboard())

@dp.message(F.text == "⬅️ Orqaga")
async def back_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu.", reply_markup=main_keyboard())

# =========================================================
# USER FEATURES (BALANS, YECHISH, TOP 10, YO'RIQNOMA)
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
        f"👤 Taklif qilgan do'stlaringiz: {count} ta\n"
        f"💵 Har bir taklif uchun bonus: {int(ref_bonus):,} so'm",
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

@dp.message(F.text == "ℹ️ Yo'riqnoma")
async def guide_handler(message: types.Message):
    warning = get_setting("warning_text")
    await message.answer(
        f"📌 **Botdan foydalanish tartibi:**\n\n"
        f"1. 💠 **Ovoz berish** tugmasini bosing.\n"
        f"2. Telefon raqamingizni kiriting va ko'rsatilgan loyihaga ovoz bering.\n"
        f"3. Ovoz berganingiz haqidagi skrinshotni botga yuboring.\n"
        f"4. Admin tasdiqlagach balansingizga pul tushadi!\n\n"
        f"{warning}",
        parse_mode="Markdown"
    )

# =========================================================
# PUL YECHISH ALGORITMI (TASTIQ, CHEK VA OTZYV BAZASI)
# =========================================================

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
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_withdraw"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_withdraw")
        ]
    ])

    await message.answer(
        f"❓ **Rostdan ham {amount:,} so'm yechib olmoqchimisiz?**\n\n"
        f"💳 **Karta yoki Nomer:** `{req}`\n"
        f"👤 **ID:** `{message.from_user.id}`\n"
        f"💰 **Qancha:** {amount:,} so'm",
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
# ADMIN PAYMENT APPROVAL & PROOF SYSTEM
# =========================================================

@dp.callback_query(F.data.startswith("pay_no_"))
async def admin_reject_pay(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

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
    if call.from_user.id != ADMIN_ID:
        return

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
    await message.answer("✍️ Text yozing (masalan: *Rahmat, ishonch uchun!*):")

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
            caption=f"🎉 **To'lovingiz muvaffaqiyatli amalga oshirildi!**\n\n💰 Summa: {amount:,} so'm\n💬 {text_to_user}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Userga chek yuborishda xato: {e}")

    try:
        review_text = (
            "💳 **MUVAFFAQIYATLI TO'LOV!**\n\n"
            f"👤 **User ID:** `{target_id}`\n"
            f"💰 **Yechib olingan summa:** {amount:,} so'm\n"
            "✅ O'tkazma muvaffaqiyatli bajarildi."
        )
        await bot.send_photo(CHANNEL_ID, photo=photo_id, caption=review_text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Kanalga otzyv yuborishda xato: {e}")

    await state.clear()
    await message.answer("✅ Chek va matn foydalanuvchiga va guruh/kanalga muvaffaqiyatli yuborildi!", reply_markup=admin_keyboard())

# =========================================================
# OVOZ BERISH & SCREENSHOT
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
    await message.answer("📞 Ovoz berish uchun telefon raqamingizni yuboring:", reply_markup=phone_keyboard())

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

    text = f"📞 Telefon: {phone}\n💵 Har bir ovoz uchun: {int(vote_price):,} so'm\n\n"
    buttons = []
    for pid, title, link in projects:
        text += f"🎯 {title}\n"
        buttons.append([InlineKeyboardButton(text=f"🎯 {title}", url=link)])

    buttons.append([InlineKeyboardButton(text="📸 Screenshot yuborish", callback_data="send_screenshot")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "send_screenshot")
async def screenshot_start(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_screenshot)
    await call.message.answer("📸 Ovoz berganingiz haqidagi screenshotni rasm ko'rinishida yuboring:")
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
        caption=f"📸 **Yangi ovoz skrinshoti**\n👤 ID: `{user_id}`\n📞 Tel: `{phone}`",
        reply_markup=admin_buttons,
        parse_mode="Markdown"
    )

    await message.answer("✅ Screenshot adminga yuborildi. Tekshirilgach balansingizga pul o'tkaziladi.", reply_markup=main_keyboard())
    await state.clear()

@dp.callback_query(F.data.startswith("approve_"))
async def approve_vote(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    target_user_id = int(call.data.split("_")[1])
    vote_price = int(get_setting("vote_price") or 5000)

    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (vote_price, target_user_id))
    conn.commit()

    try:
        await bot.send_message(target_user_id, f"🎉 Ovozingiz tasdiqlandi! Balansingizga +{vote_price:,} so'm qo'shildi.")
    except Exception:
        pass

    await call.message.edit_caption(caption=call.message.caption + "\n\n✅ TASDIQLANDI")
    await call.answer("Tasdiqlandi!")

@dp.callback_query(F.data.startswith("reject_"))
async def reject_vote(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    target_user_id = int(call.data.split("_")[1])
    try:
        await bot.send_message(target_user_id, "❌ Yuborgan screenshotingiz rad etildi.")
    except Exception:
        pass
    await call.message.edit_caption(caption=call.message.caption + "\n\n❌ RAD ETILDI")
    await call.answer("Rad etildi!")

# =========================================================
# FULL ADMIN PANEL & SETTINGS MANAGEMENT
# =========================================================

@dp.message(Command("admin"))
async def admin_command(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 **Admin Panelga Xush Kelibsiz!**", reply_markup=admin_keyboard(), parse_mode="Markdown")

@dp.message(F.text == "❌ Admin paneldan chiqish")
async def admin_exit(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Asosiy menyu.", reply_markup=main_keyboard())

@dp.message(F.text == "⚙️ Bot Sozlamalari")
async def admin_settings_menu(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("⚙️ O'zgartirmoqchi bo'lgan sozlamangizni tanlang:", reply_markup=settings_keyboard())

@dp.message(F.text == "⬅️ Admin panel")
async def back_to_admin(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 Admin Panel", reply_markup=admin_keyboard())

# --- Loyiha qo'shish va o'chirish ---

@dp.message(F.text == "➕ Loyiha qo'shish")
async def add_project_start(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.set_state(AdminStates.project_title)
        await message.answer("🎯 Loyiha nomini kiriting:", reply_markup=back_keyboard())

@dp.message(AdminStates.project_title)
async def add_project_title(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Admin panel.", reply_markup=admin_keyboard())
        return

    await state.update_data(title=message.text)
    await state.set_state(AdminStates.project_link)
    await message.answer("🔗 Loyiha havolasini (link) kiriting:")

@dp.message(AdminStates.project_link)
async def add_project_link(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Admin panel.", reply_markup=admin_keyboard())
        return

    data = await state.get_data()
    cursor.execute("INSERT INTO projects (title, link) VALUES (?, ?)", (data["title"], message.text))
    conn.commit()

    await state.clear()
    await message.answer("✅ Loyiha muvaffaqiyatli qo'shildi!", reply_markup=admin_keyboard())

@dp.message(F.text == "🗑 Loyihalarni o'chirish")
async def list_projects_delete(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        cursor.execute("SELECT id, title FROM projects WHERE is_active = 1")
        projects = cursor.fetchall()

        if not projects:
            await message.answer("Xozirda o'chirish uchun loyihalar yo'q.")
            return

        keyboard = []
        for pid, title in projects:
            keyboard.append([InlineKeyboardButton(text=f"❌ {title}", callback_data=f"del_proj_{pid}")])

        await message.answer("O'chirmoqchi bo'lgan loyihangizni bosing:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@dp.callback_query(F.data.startswith("del_proj_"))
async def delete_project_cb(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    pid = int(call.data.split("_")[2])
    cursor.execute("UPDATE projects SET is_active = 0 WHERE id = ?", (pid,))
    conn.commit()

    await call.message.edit_text("✅ Loyiha o'chirib tashlandi!")
    await call.answer()

# --- Dynamic Settings Update Handlers ---

@dp.message(F.text == "📝 Start matni")
async def set_start_text_start(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.set_state(AdminStates.set_start_text)
        await message.answer("Yangi /start matnini yuboring:", reply_markup=back_keyboard())

@dp.message(AdminStates.set_start_text)
async def set_start_text_save(message: types.Message, state: FSMContext):
    set_setting("start_text", message.text)
    await state.clear()
    await message.answer("✅ Start matni yangilandi!", reply_markup=settings_keyboard())

@dp.message(F.text == "💵 Ovoz narxi")
async def set_vote_price_start(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.set_state(AdminStates.set_vote_price)
        await message.answer("Har bir ovoz uchun yangi narxni (faqat raqamda) kiriting:", reply_markup=back_keyboard())

@dp.message(AdminStates.set_vote_price)
async def set_vote_price_save(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Raqam yozing!")
        return
    set_setting("vote_price", message.text)
    await state.clear()
    await message.answer("✅ Ovoz narxi yangilandi!", reply_markup=settings_keyboard())

@dp.message(F.text == "👥 Referal bonusi")
async def set_ref_bonus_start(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.set_state(AdminStates.set_ref_bonus)
        await message.answer("Yangi referal bonusini (faqat raqamda) kiriting:", reply_markup=back_keyboard())

@dp.message(AdminStates.set_ref_bonus)
async def set_ref_bonus_save(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Raqam yozing!")
        return
    set_setting("referral_bonus", message.text)
    await state.clear()
    await message.answer("✅ Referal bonusi yangilandi!", reply_markup=settings_keyboard())

@dp.message(F.text == "💳 Min yechish summasi")
async def set_min_withdraw_start(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.set_state(AdminStates.set_min_withdraw)
        await message.answer("Yangi minimal pul yechish summasini (faqat raqamda) kiriting:", reply_markup=back_keyboard())

@dp.message(AdminStates.set_min_withdraw)
async def set_min_withdraw_save(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Raqam yozing!")
        return
    set_setting("min_withdraw", message.text)
    await state.clear()
    await message.answer("✅ Minimal yechish summasi yangilandi!", reply_markup=settings_keyboard())

# --- Statistika va Reklama ---

@dp.message(F.text == "📊 Statistika")
async def admin_stats(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(balance) FROM users")
        total_balance = cursor.fetchone()[0] or 0

        await message.answer(
            f"📊 **BOT STATISTIKASI**\n\n"
            f"👥 Umumiy foydalanuvchilar: {total_users} ta\n"
            f"💰 Jami foydalanuvchilar balanslari: {total_balance:,} so'm",
            parse_mode="Markdown"
        )

@dp.message(F.text == "📢 Reklama yuborish")
async def broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.set_state(AdminStates.broadcast_msg)
        await message.answer("Barcha foydalanuvchilarga yuboriladigan xabar/reklamani kiriting:", reply_markup=back_keyboard())

@dp.message(AdminStates.broadcast_msg)
async def broadcast_send(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Admin panel.", reply_markup=admin_keyboard())
        return

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    count = 0
    await message.answer("🚀 Reklama yuborilmoqda...")
    for (uid,) in users:
        try:
            await message.copy_to(chat_id=uid)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await state.clear()
    await message.answer(f"✅ Reklama {count} ta foydalanuvchiga muvaffaqiyatli yetkazildi!", reply_markup=admin_keyboard())

# =========================================================
# MAIN ENGINE
# =========================================================

async def main():
    logging.info("OpenBudget bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
