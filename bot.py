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
# SETTINGS
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID topilmadi!")

# =========================================================
# DATABASE
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

# Boshlang'ich default sozlamalar
default_settings = {
    "start_text": "Assalomu alaykum! 👋\n\n💠 OpenBudget botiga xush kelibsiz!\n\nKerakli bo'limni tanlang 👇",
    "start_photo": "",
    "no_project_text": "⏳ Hozircha ovoz berish boshlanmagan.\n\nFaol loyihalar paydo bo'lganda shu yerda ko'rinadi.",
    "warning_text": "⚠️ **OGOHLANTIRISH:**\nOvoz berishda faqat haqiqiy raqam va to'g'ri screenshot yuboring! Qalbaki screenshotlar bloklanadi.",
    "warning_photo": "",
    "referral_bonus": "1000",
    "vote_price": "5000",
    "min_withdraw": "10000"
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
# BOT
# =========================================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# =========================================================
# STATES
# =========================================================

class UserStates(StatesGroup):
    waiting_phone = State()
    waiting_screenshot = State()

class AdminStates(StatesGroup):
    project_title = State()
    project_link = State()

    broadcast_photo = State()
    broadcast_text = State()

    change_start_text = State()
    change_start_photo = State()
    change_no_project_text = State()
    change_warning_text = State()
    change_warning_photo = State()
    change_referral_bonus = State()
    change_vote_price = State()
    change_min_withdraw = State()

# =========================================================
# KEYBOARDS
# =========================================================

def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💠 Ovoz berish")],
            [KeyboardButton(text="💵 Balansim"), KeyboardButton(text="👥 Referal")],
            [KeyboardButton(text="📊 Top 10"), KeyboardButton(text="⚙️ Sozlamalar")]
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
            [KeyboardButton(text="📢 Reklama yuborish")],
            [KeyboardButton(text="❌ Admin paneldan chiqish")]
        ],
        resize_keyboard=True
    )

def admin_settings_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Start Matni"), KeyboardButton(text="🖼 Start Rasmi")],
            [KeyboardButton(text="⚠️ Ogohlantirish Matni"), KeyboardButton(text="🖼 Ogohlantirish Rasmi")],
            [KeyboardButton(text="📭 Loyiha yo'q Matni")],
            [KeyboardButton(text="💰 Referal Summa"), KeyboardButton(text="💵 Ovoz Puli")],
            [KeyboardButton(text="💳 Minimal Yechish")],
            [KeyboardButton(text="⬅️ Orqaga")]
        ],
        resize_keyboard=True
    )

def back_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Orqaga")]],
        resize_keyboard=True
    )

# =========================================================
# HELPERS
# =========================================================

def is_admin(user_id):
    return user_id == ADMIN_ID

async def add_user(user_id, referrer_id=None):
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        ref_id = referrer_id if (referrer_id and referrer_id != user_id) else None
        cursor.execute(
            "INSERT INTO users (user_id, referrer_id, balance, is_banned, advertising) VALUES (?, ?, 0, 0, 1)",
            (user_id, ref_id)
        )
        if ref_id:
            ref_bonus = int(get_setting("referral_bonus") or 0)
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (ref_bonus, ref_id))
        conn.commit()
        return True
    return False

def normalize_phone(phone):
    phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if phone.startswith("+998") and len(phone) == 13 and phone[1:].isdigit():
        return phone
    if phone.startswith("998") and len(phone) == 12 and phone.isdigit():
        return "+" + phone
    if len(phone) == 9 and phone.isdigit():
        return "+998" + phone
    return None

# =========================================================
# START
# =========================================================

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    await add_user(user_id, referrer_id)

    start_text = get_setting("start_text")
    start_photo = get_setting("start_photo")

    if start_photo:
        try:
            await message.answer_photo(
                photo=start_photo,
                caption=start_text,
                reply_markup=main_keyboard()
            )
            return
        except Exception:
            pass

    await message.answer(start_text, reply_markup=main_keyboard())

# =========================================================
# BACK
# =========================================================

@dp.message(F.text == "⬅️ Orqaga")
async def back_handler(message: types.Message, state: FSMContext):
    await state.clear()
    if is_admin(message.from_user.id):
        await message.answer("Admin panel.", reply_markup=admin_keyboard())
    else:
        await message.answer("Asosiy menyu.", reply_markup=main_keyboard())

# =========================================================
# BALANCE
# =========================================================

@dp.message(F.text == "💵 Balansim")
async def balance_handler(message: types.Message):
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
    row = cursor.fetchone()
    balance = row[0] if row else 0
    min_w = get_setting("min_withdraw")

    await message.answer(
        f"💰 Balansingiz: {balance:,} so'm\n"
        f"💳 Minimal yechib olish: {int(min_w):,} so'm"
    )

# =========================================================
# REFERRAL
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
        f"🔗 Sizning havolangiz:\n`{link}`\n\n"
        f"👤 Taklif qilganlaringiz: {count} ta\n"
        f"💵 Har bir taklif uchun: {int(ref_bonus):,} so'm",
        parse_mode="Markdown"
    )

# =========================================================
# VOICE / PROJECTS
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
    await message.answer(
        "📞 Ovoz berish uchun telefon raqamingizni yuboring.\n\n"
        "Raqam quyidagi formatda bo'lishi mumkin:\n+998991234567 yoki 991234567",
        reply_markup=phone_keyboard()
    )

@dp.message(UserStates.waiting_phone, F.contact)
async def phone_contact_handler(message: types.Message, state: FSMContext):
    phone = normalize_phone(message.contact.phone_number)
    if not phone:
        await message.answer("❌ Telefon raqami noto'g'ri.")
        return
    await save_phone_and_show_projects(message, phone, state)

@dp.message(UserStates.waiting_phone, F.text)
async def phone_text_handler(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Asosiy menyu.", reply_markup=main_keyboard())
        return

    phone = normalize_phone(message.text)
    if not phone:
        await message.answer("❌ Raqam noto'g'ri. Masalan: +998991234567 yoki 991234567")
        return

    await save_phone_and_show_projects(message, phone, state)

async def save_phone_and_show_projects(message, phone, state):
from aiogram.types import InputMediaPhoto

async def save_phone_and_show_projects(message, phone, state):
    cursor.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, message.from_user.id))
    conn.commit()

    cursor.execute("SELECT id, title, link FROM projects WHERE is_active = 1 ORDER BY id DESC")
    projects = cursor.fetchall()

    warning_text = get_setting("warning_text")
    warning_photo = get_setting("warning_photo")  # Birinchi rasm ID si
    second_photo = get_setting("start_photo")    # Ikkinchi rasm ID si (yoki o'zingiz xohlagan 2-rasm)
    vote_price = get_setting("vote_price")

    text = f"📞 Raqamingiz: {phone}\n\n"
    text += f"💵 Har bir ovoz uchun: {int(vote_price):,} so'm beriladi.\n\n"
    if warning_text:
        text += f"{warning_text}\n\n"
    text += "📋 **Ovoz berish loyihalari:**\n\n"

    buttons = []
    for project_id, title, link in projects:
        text += f"🎯 {title}\n🔗 Ovoz berish havolasi pastda\n\n"
        buttons.append([InlineKeyboardButton(text=f"🎯 {title}", url=link)])

    buttons.append([InlineKeyboardButton(text="📸 Ovoz berdim — screenshot yuborish", callback_data="send_screenshot")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    # Agar 2 ta rasm ham mavjud bo'lsa, ularni albom qilib birga yuboramiz
    if warning_photo and second_photo:
        try:
            media = [
                InputMediaPhoto(media=warning_photo),
                InputMediaPhoto(media=second_photo)
            ]
            # 2 ta rasmni albom qilib birga yuborish
            await message.answer_media_group(media=media)
            # Rasmlar tegidan matn va tugmalarni yuborish
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
            return
        except Exception:
            pass

    # Agar rasmlar bo'lmasa yoki xatolik bo'lsa, shunchaki matn va tugmalar chiqadi
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


# =========================================================
# SCREENSHOT
# =========================================================

@dp.callback_query(F.data == "send_screenshot")
async def screenshot_start(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_screenshot)
    await call.message.answer("📸 Ovoz berganingizni tasdiqlovchi screenshotni yuboring.")
    await call.answer()

@dp.message(UserStates.waiting_screenshot, F.photo)
async def receive_screenshot(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    cursor.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    phone = row[0] if row else "Noma'lum"

    cursor.execute("SELECT title FROM projects WHERE is_active = 1 ORDER BY id DESC")
    project_rows = cursor.fetchall()
    project_text = ", ".join([x[0] for x in project_rows])

    caption = (
        "📸 **Yangi ovoz screenshot**\n\n"
        f"👤 User ID: `{user_id}`\n"
        f"📞 Telefon: {phone}\n"
        f"🎯 Faol loyihalar: {project_text or 'Yo‘q'}"
    )

    photo_id = message.photo[-1].file_id
    await bot.send_photo(ADMIN_ID, photo=photo_id, caption=caption, parse_mode="Markdown")

    await message.answer(
        "✅ Screenshot adminga yuborildi.\n\nTekshiruvdan so'ng balansingizga pul qo'shiladi.",
        reply_markup=main_keyboard()
    )
    await state.clear()

@dp.message(UserStates.waiting_screenshot)
async def wrong_screenshot(message: types.Message):
    await message.answer("📸 Iltimos, screenshotni rasm sifatida yuboring.")

# =========================================================
# ADMIN PANEL
# =========================================================

@dp.message(Command("admin"))
async def admin_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("👑 ADMIN PANEL", reply_markup=admin_keyboard())

@dp.message(F.text == "❌ Admin paneldan chiqish")
async def admin_exit(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Asosiy menyu.", reply_markup=main_keyboard())

# =========================================================
# LOYIHALARNI BO'SHATISH VA YANGI QO'SHISH
# =========================================================

@dp.message(F.text == "🗑 Loyihalarni o'chirish")
async def clear_projects(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    cursor.execute("DELETE FROM projects")
    conn.commit()
    await message.answer("🗑 Barcha loyihalar muvaffaqiyatli o'chirildi! Endi yangi loyiha qo'shishingiz mumkin.")

@dp.message(F.text == "➕ Loyiha qo'shish")
async def add_project_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminStates.project_title)
    await message.answer("🎯 Loyiha nomini yozing:", reply_markup=back_keyboard())

@dp.message(AdminStates.project_title)
async def add_project_title(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Admin panel.", reply_markup=admin_keyboard())
        return

    await state.update_data(title=message.text.strip())
    await state.set_state(AdminStates.project_link)
    await message.answer("🔗 Endi loyiha linkini yuboring:")

@dp.message(AdminStates.project_link)
async def add_project_link(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Admin panel.", reply_markup=admin_keyboard())
        return

    link = message.text.strip()
    if not link.startswith(("http://", "https://", "tg://")):
        await message.answer("❌ Link noto'g'ri. https:// bilan boshlansin.")
        return

    data = await state.get_data()
    cursor.execute("INSERT INTO projects (title, link, is_active) VALUES (?, ?, 1)", (data["title"], link))
    conn.commit()

    await state.clear()
    await message.answer("✅ Yangi loyiha muvaffaqiyatli qo'shildi!", reply_markup=admin_keyboard())

# =========================================================
# BOT SOZLAMALARI (ADMIN)
# =========================================================

@dp.message(F.text == "⚙️ Bot Sozlamalari")
async def admin_settings_menu(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("⚙️ O'zgartirmoqchi bo'lgan sozlamangizni tanlang:", reply_markup=admin_settings_keyboard())

# 1. Start Matni
@dp.message(F.text == "📝 Start Matni")
async def change_start_text_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.set_state(AdminStates.change_start_text)
    await message.answer("Yangi start matnini kiriting:", reply_markup=back_keyboard())

@dp.message(AdminStates.change_start_text)
async def change_start_text_save(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Sozlamalar.", reply_markup=admin_settings_keyboard())
        return
    set_setting("start_text", message.text)
    await state.clear()
    await message.answer("✅ Start matni yangilandi!", reply_markup=admin_settings_keyboard())

# 2. Start Rasmi
@dp.message(F.text == "🖼 Start Rasmi")
async def change_start_photo_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.set_state(AdminStates.change_start_photo)
    await message.answer("Start uchun rasm yuboring (O'chirish uchun /del_photo yozing):", reply_markup=back_keyboard())

@dp.message(AdminStates.change_start_photo)
async def change_start_photo_save(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Sozlamalar.", reply_markup=admin_settings_keyboard())
        return
    if message.text == "/del_photo":
        set_setting("start_photo", "")
        await state.clear()
        await message.answer("✅ Start rasmi olib tashlandi!", reply_markup=admin_settings_keyboard())
        return
    if message.photo:
        photo_id = message.photo[-1].file_id
        set_setting("start_photo", photo_id)
        await state.clear()
        await message.answer("✅ Start rasmi yangilandi!", reply_markup=admin_settings_keyboard())
    else:
        await message.answer("Iltimos, rasm yuboring yoki /del_photo yozing.")

# 3. Ogohlantirish Matni
@dp.message(F.text == "⚠️ Ogohlantirish Matni")
async def change_warning_text_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.set_state(AdminStates.change_warning_text)
    await message.answer("Yangi ogohlantirish matnini yuboring:", reply_markup=back_keyboard())

@dp.message(AdminStates.change_warning_text)
async def change_warning_text_save(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Sozlamalar.", reply_markup=admin_settings_keyboard())
        return
    set_setting("warning_text", message.text)
    await state.clear()
    await message.answer("✅ Ogohlantirish matni yangilandi!", reply_markup=admin_settings_keyboard())

# 4. Ogohlantirish Rasmi
@dp.message(F.text == "🖼 Ogohlantirish Rasmi")
async def change_warning_photo_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.set_state(AdminStates.change_warning_photo)
    await message.answer("Ogohlantirish uchun rasm yuboring (O'chirish uchun /del_photo yozing):", reply_markup=back_keyboard())

@dp.message(AdminStates.change_warning_photo)
async def change_warning_photo_save(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Sozlamalar.", reply_markup=admin_settings_keyboard())
        return
    if message.text == "/del_photo":
        set_setting("warning_photo", "")
        await state.clear()
        await message.answer("✅ Ogohlantirish rasmi olib tashlandi!", reply_markup=admin_settings_keyboard())
        return
    if message.photo:
        photo_id = message.photo[-1].file_id
        set_setting("warning_photo", photo_id)
        await state.clear()
        await message.answer("✅ Ogohlantirish rasmi yangilandi!", reply_markup=admin_settings_keyboard())
    else:
        await message.answer("Iltimos, rasm yuboring yoki /del_photo yozing.")

# 5. Loyiha Yo'q Matni
@dp.message(F.text == "📭 Loyiha yo'q Matni")
async def change_no_project_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.set_state(AdminStates.change_no_project_text)
    await message.answer("Loyihalar bo'lmaganda chiqadigan matnni yozing:", reply_markup=back_keyboard())

@dp.message(AdminStates.change_no_project_text)
async def change_no_project_save(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Sozlamalar.", reply_markup=admin_settings_keyboard())
        return
    set_setting("no_project_text", message.text)
    await state.clear()
    await message.answer("✅ Matn yangilandi!", reply_markup=admin_settings_keyboard())

# 6. Referal Summasi
@dp.message(F.text == "💰 Referal Summa")
async def change_ref_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.set_state(AdminStates.change_referral_bonus)
    await message.answer("Referal summasini kiriting (masalan: 1000):", reply_markup=back_keyboard())

@dp.message(AdminStates.change_referral_bonus)
async def change_ref_save(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Sozlamalar.", reply_markup=admin_settings_keyboard())
        return
    if message.text.isdigit():
        set_setting("referral_bonus", message.text)
        await state.clear()
        await message.answer("✅ Referal summasi yangilandi!", reply_markup=admin_settings_keyboard())
    else:
        await message.answer("Iltimos, faqat raqam kiriting!")

# 7. Ovoz Puli
@dp.message(F.text == "💵 Ovoz Puli")
async def change_vote_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.set_state(AdminStates.change_vote_price)
    await message.answer("Ovoz puli summasini kiriting (masalan: 5000):", reply_markup=back_keyboard())

@dp.message(AdminStates.change_vote_price)
async def change_vote_save(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Sozlamalar.", reply_markup=admin_settings_keyboard())
        return
    if message.text.isdigit():
        set_setting("vote_price", message.text)
        await state.clear()
        await message.answer("✅ Ovoz puli summasi yangilandi!", reply_markup=admin_settings_keyboard())
    else:
        await message.answer("Iltimos, faqat raqam kiriting!")

# 8. Minimal Yechish
@dp.message(F.text == "💳 Minimal Yechish")
async def change_min_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.set_state(AdminStates.change_min_withdraw)
    await message.answer("Minimal yechish summasini kiriting (masalan: 10000):", reply_markup=back_keyboard())

@dp.message(AdminStates.change_min_withdraw)
async def change_min_save(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Sozlamalar.", reply_markup=admin_settings_keyboard())
        return
    if message.text.isdigit():
        set_setting("min_withdraw", message.text)
        await state.clear()
        await message.answer("✅ Minimal yechish summasi yangilandi!", reply_markup=admin_settings_keyboard())
    else:
        await message.answer("Iltimos, faqat raqam kiriting!")

# =========================================================
# STATISTIKA & REKLAMA
# =========================================================

@dp.message(F.text == "📊 Statistika")
async def statistics(message: types.Message):
    if not is_admin(message.from_user.id): return
    cursor.execute("SELECT COUNT(*) FROM users")
    users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE phone IS NOT NULL AND phone != ''")
    phones = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM projects WHERE is_active = 1")
    active_projects = cursor.fetchone()[0]

    await message.answer(
        "📊 **BOT STATISTIKASI**\n\n"
        f"👥 Foydalanuvchilar: {users}\n"
        f"📞 Telefon kiritganlar: {phones}\n"
        f"🎯 Faol loyihalar: {active_projects}"
    )

@dp.message(F.text == "📢 Reklama yuborish")
async def broadcast_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.set_state(AdminStates.broadcast_photo)
    await message.answer("📸 Reklama uchun rasm yuboring.\n\nAgar rasm kerak bo'lmasa, /skip yozing.", reply_markup=back_keyboard())

@dp.message(AdminStates.broadcast_photo)
async def broadcast_photo(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Admin panel.", reply_markup=admin_keyboard())
        return

    if message.text == "/skip":
        await state.update_data(photo=None)
    elif message.photo:
        await state.update_data(photo=message.photo[-1].file_id)
    else:
        await message.answer("📸 Rasm yuboring yoki /skip yozing.")
        return

    await state.set_state(AdminStates.broadcast_text)
    await message.answer("✍️ Endi reklama matnini yuboring:")

@dp.message(AdminStates.broadcast_text)
async def broadcast_text(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Orqaga":
        await state.clear()
        await message.answer("Admin panel.", reply_markup=admin_keyboard())
        return

    text = message.text.strip()
    data = await state.get_data()
    photo = data.get("photo")
    await state.clear()

    cursor.execute("SELECT user_id FROM users WHERE is_banned = 0 AND advertising = 1")
    users = cursor.fetchall()

    success, failed = 0, 0
    await message.answer(f"📢 Reklama {len(users)} ta foydalanuvchiga yuborilmoqda...")

    for (user_id,) in users:
        try:
            if photo:
                await bot.send_photo(user_id, photo=photo, caption=text)
            else:
                await bot.send_message(user_id, text)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await message.answer(
        f"📢 Reklama tugadi!\n\n✅ Yuborildi: {success}\n❌ Yuborilmadi: {failed}",
        reply_markup=admin_keyboard()
    )

# =========================================================
# TOP 10 & USER SETTINGS
# =========================================================

@dp.message(F.text == "⚙️ Sozlamalar")
async def user_settings(message: types.Message):
    cursor.execute("SELECT advertising FROM users WHERE user_id = ?", (message.from_user.id,))
    row = cursor.fetchone()
    advertising = row[0] if row else 1
    status = "🟢 Yoqilgan" if advertising else "🔴 O'chirilgan"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔄 Reklamani o'zgartirish", callback_data="toggle_ads")
    ]])
    await message.answer(f"⚙️ Sozlamalar\n\n📢 Reklama xabarlari: {status}", reply_markup=keyboard)

@dp.callback_query(F.data == "toggle_ads")
async def toggle_ads(call: types.CallbackQuery):
    cursor.execute("SELECT advertising FROM users WHERE user_id = ?", (call.from_user.id,))
    row = cursor.fetchone()
    current = row[0] if row else 1
    new_value = 0 if current else 1

    cursor.execute("UPDATE users SET advertising = ? WHERE user_id = ?", (new_value, call.from_user.id))
    conn.commit()

    status = "🟢 Yoqildi" if new_value else "🔴 O'chirildi"
    await call.message.edit_text(f"📢 Reklama xabarlari: {status}")
    await call.answer()

@dp.message(F.text == "📊 Top 10")
async def top_users(message: types.Message):
    cursor.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    rows = cursor.fetchall()
    text = "🏆 **TOP 10 FOYDALANUVCHILAR**\n\n"
    for index, (uid, balance) in enumerate(rows, 1):
        text += f"{index}. `{uid}` — {balance:,} so'm\n"
    await message.answer(text, parse_mode="Markdown")

# =========================================================
# RUN
# =========================================================

async def main():
    logging.info("OpenBudget bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
