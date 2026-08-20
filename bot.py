import asyncio
import logging
import os
import sqlite3

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable topilmadi!")

conn = sqlite3.connect("openbudget_bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    referrer_id INTEGER,
    is_banned INTEGER DEFAULT 0
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    link TEXT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    card_number TEXT,
    status TEXT DEFAULT 'pending'
)""")
conn.commit()

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class AdminStates(StatesGroup):
    add_channel = State()
    add_project_title = State()
    add_project_link = State()


class UserStates(StatesGroup):
    withdraw_card = State()
    withdraw_amount = State()


def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💠 Ovoz berish")],
            [KeyboardButton(text="💵 Balansim"), KeyboardButton(text="👑 Pul yechish")],
            [KeyboardButton(text="👥 Referal"), KeyboardButton(text="🌐 To'lovlar tarixi")],
            [KeyboardButton(text="📊 Top 10")]
        ],
        resize_keyboard=True
    )


def admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Loyiha qo'shish"), KeyboardButton(text="📢 Kanal qo'shish")],
            [KeyboardButton(text="💳 Pul yechish so'rovlari"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="❌ Menuga qaytish")]
        ],
        resize_keyboard=True
    )


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)
    referrer_id = None

    if len(parts) == 2 and parts[1].isdigit():
        candidate = int(parts[1])
        if candidate != user_id:
            referrer_id = candidate

    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()

    if not exists:
        cursor.execute(
            "INSERT INTO users (user_id, balance, referrer_id) VALUES (?, 0, ?)",
            (user_id, referrer_id)
        )

        if referrer_id:
            cursor.execute(
                "UPDATE users SET balance = balance + 1000 WHERE user_id = ?",
                (referrer_id,)
            )
            try:
                await bot.send_message(
                    referrer_id,
                    "🎉 Taklif qilgan do'stingiz botga kirdi! Sizga +1000 so'm berildi."
                )
            except Exception:
                pass
        conn.commit()

    welcome_text = (
        "Assalomu alaykum! 💠 OpenBudget botiga xush kelibsiz.\n\n"
        "OpenBudget 22-avgust kunidan boshlab ishga tushadi ✅\n\n"
        "Siz ungacha do'stlaringizni botga taklif qilib, har bir do'stingiz uchun "
        "+1000 so'mdan ishlab olasiz. Ovoz berish boshlanganda esa do'stingizning "
        "har bir ovozidan yana 5000 so'm olasiz ⚡️\n\n"
        "Kerakli bo'limni menyudan tanlang 👇"
    )
    await message.answer(welcome_text, reply_markup=main_keyboard())


@dp.message(F.text == "💵 Balansim")
async def show_balance(message: types.Message):
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
    res = cursor.fetchone()
    balance = res[0] if res else 0
    await message.answer(f"💰 Sizning hisobingiz: {balance} so'm")


@dp.message(F.text == "👥 Referal")
async def show_referral(message: types.Message):
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"

    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE referrer_id = ?",
        (message.from_user.id,)
    )
    count = cursor.fetchone()[0]

    text = (
        f"🔗 Sizning referal havolangiz:\n`{ref_link}`\n\n"
        f"📊 Siz taklif qilgan a'zolar soni: {count} ta\n"
        "🎁 Har bir taklif qilgan do'stingiz uchun 1000 so'm beriladi!"
    )
    await message.answer(text, parse_mode="Markdown")


@dp.message(F.text == "💠 Ovoz berish")
async def show_projects(message: types.Message):
    cursor.execute("SELECT title, link FROM projects")
    projects = cursor.fetchall()

    if not projects:
        await message.answer("Hozircha ovoz berish uchun faol loyihalar yo'q.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=title, url=link)]
        for title, link in projects
    ])

    await message.answer(
        "📋 Ovoz berish mumkin bo'lgan loyihalar:",
        reply_markup=keyboard
    )


@dp.message(F.text == "📊 Top 10")
async def show_top(message: types.Message):
    cursor.execute(
        "SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10"
    )
    top_users = cursor.fetchall()

    text = "🏆 Top 10 eng ko'p balansga ega foydalanuvchilar:\n\n"
    for idx, (uid, bal) in enumerate(top_users, 1):
        text += f"{idx}. ID: `{uid}` — {bal} so'm\n"

    await message.answer(text, parse_mode="Markdown")


@dp.message(F.text == "🌐 To'lovlar tarixi")
async def show_history(message: types.Message):
    cursor.execute(
        """SELECT amount, card_number, status
           FROM withdrawals
           WHERE user_id = ?
           ORDER BY id DESC LIMIT 5""",
        (message.from_user.id,)
    )
    history = cursor.fetchall()

    if not history:
        await message.answer("Sizda hali to'lovlar tarixi mavjud emas.")
        return

    text = "📜 Oxirgi to'lov so'rovlaringiz:\n\n"
    for amount, card, status in history:
        text += (
            f"💳 Karta: {card}\n"
            f"💰 Summa: {amount} so'm\n"
            f"📌 Holat: {status}\n"
            "------------------\n"
        )

    await message.answer(text)


@dp.message(F.text == "👑 Pul yechish")
async def withdraw_start(message: types.Message, state: FSMContext):
    cursor.execute(
        "SELECT balance FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )
    row = cursor.fetchone()
    balance = row[0] if row else 0

    if balance < 10000:
        await message.answer("❌ Minimal pul yechish summasi 10,000 so'm!")
        return

    await message.answer("💳 Plastik karta raqamingizni kiriting:")
    await state.set_state(UserStates.withdraw_card)


@dp.message(UserStates.withdraw_card)
async def process_withdraw_card(message: types.Message, state: FSMContext):
    card = message.text.strip().replace(" ", "").replace("-", "")
    if not card.isdigit() or not 12 <= len(card) <= 19:
        await message.answer("❌ Karta raqamini to'g'ri kiriting.")
        return

    await state.update_data(card=card)
    await message.answer("💰 Yechib olmoqchi bo'lgan summangizni kiriting:")
    await state.set_state(UserStates.withdraw_amount)


@dp.message(UserStates.withdraw_amount)
async def process_withdraw_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Summani faqat raqam bilan kiriting.")
        return

    amount = int(message.text)
    if amount < 10000:
        await message.answer("❌ Minimal yechish summasi 10,000 so'm.")
        return

    user_data = await state.get_data()
    card = user_data["card"]

    cursor.execute(
        "SELECT balance FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )
    row = cursor.fetchone()
    balance = row[0] if row else 0

    if amount > balance:
        await message.answer("❌ Balansda yetarli mablag' yo'q.")
        return

    cursor.execute(
        "UPDATE users SET balance = balance - ? WHERE user_id = ?",
        (amount, message.from_user.id)
    )
    cursor.execute(
        """INSERT INTO withdrawals (user_id, amount, card_number)
           VALUES (?, ?, ?)""",
        (message.from_user.id, amount, card)
    )
    conn.commit()

    await message.answer(
        "✅ So'rov adminga yuborildi. Tez orada pulingiz o'tkaziladi."
    )
    await state.clear()


@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("👑 Admin Panel", reply_markup=admin_keyboard())


@dp.message(F.text == "❌ Menuga qaytish")
async def back_to_main(message: types.Message):
    await message.answer("Asosiy menuga qaytdingiz.", reply_markup=main_keyboard())


@dp.message(F.text == "📊 Statistika")
async def admin_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(balance) FROM users")
    total_balance = cursor.fetchone()[0] or 0

    await message.answer(
        f"📊 Bot statistikasi:\n\n"
        f"Jami foydalanuvchilar: {total_users} ta\n"
        f"Jami balanslar: {total_balance} so'm"
    )


@dp.message(F.text == "📢 Kanal qo'shish")
async def add_channel_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "Kanal ID yoki username kiriting (masalan: @kanal_username):"
    )
    await state.set_state(AdminStates.add_channel)


@dp.message(AdminStates.add_channel)
async def process_add_channel(message: types.Message, state: FSMContext):
    cursor.execute(
        "INSERT INTO channels (channel_id) VALUES (?)",
        (message.text.strip(),)
    )
    conn.commit()
    await message.answer("✅ Kanal muvaffaqiyatli qo'shildi!")
    await state.clear()


@dp.message(F.text == "➕ Loyiha qo'shish")
async def add_project_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await message.answer("Loyiha nomini kiriting:")
    await state.set_state(AdminStates.add_project_title)


@dp.message(AdminStates.add_project_title)
async def process_project_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await message.answer("Loyiha havolasini (link) kiriting:")
    await state.set_state(AdminStates.add_project_link)


@dp.message(AdminStates.add_project_link)
async def process_project_link(message: types.Message, state: FSMContext):
    data = await state.get_data()
    link = message.text.strip()

    if not link.startswith(("http://", "https://", "tg://")):
        await message.answer("❌ To'g'ri link kiriting.")
        return

    cursor.execute(
        "INSERT INTO projects (title, link) VALUES (?, ?)",
        (data["title"], link)
    )
    conn.commit()

    await message.answer("✅ Loyiha muvaffaqiyatli qo'shildi!")
    await state.clear()


@dp.message(F.text == "💳 Pul yechish so'rovlari")
async def list_withdrawals(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    cursor.execute(
        """SELECT id, user_id, amount, card_number
           FROM withdrawals
           WHERE status = 'pending'
           ORDER BY id ASC"""
    )
    requests = cursor.fetchall()

    if not requests:
        await message.answer("Hozircha to'lov so'rovlari yo'q.")
        return

    for req_id, uid, amount, card in requests:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Tasdiqlash",
                    callback_data=f"pay_ok_{req_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Rad etish",
                    callback_data=f"pay_no_{req_id}"
                )
            ]
        ])

        await message.answer(
            f"🆔 So'rov ID: {req_id}\n"
            f"👤 User ID: `{uid}`\n"
            f"💰 Summa: {amount} so'm\n"
            f"💳 Karta: `{card}`",
            reply_markup=kb,
            parse_mode="Markdown"
        )


@dp.callback_query(F.data.startswith("pay_ok_"))
async def approve_pay(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo'q", show_alert=True)
        return

    req_id = int(call.data.split("_")[2])

    cursor.execute(
        "SELECT status FROM withdrawals WHERE id = ?",
        (req_id,)
    )
    row = cursor.fetchone()

    if not row or row[0] != "pending":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    cursor.execute(
        "UPDATE withdrawals SET status = 'approved' WHERE id = ?",
        (req_id,)
    )
    conn.commit()

    await call.message.edit_text(
        call.message.text + "\n\n✅ To'lab berildi!"
    )
    await call.answer("Tasdiqlandi")


@dp.callback_query(F.data.startswith("pay_no_"))
async def reject_pay(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo'q", show_alert=True)
        return

    req_id = int(call.data.split("_")[2])

    cursor.execute(
        "SELECT user_id, amount, status FROM withdrawals WHERE id = ?",
        (req_id,)
    )
    row = cursor.fetchone()

    if not row or row[2] != "pending":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    uid, amount, _ = row

    cursor.execute(
        "UPDATE users SET balance = balance + ? WHERE user_id = ?",
        (amount, uid)
    )
    cursor.execute(
        "UPDATE withdrawals SET status = 'rejected' WHERE id = ?",
        (req_id,)
    )
    conn.commit()

    await call.message.edit_text(
        call.message.text + "\n\n❌ Rad etildi va pul qaytarildi!"
    )
    await call.answer("Rad etildi")


async def main():
    logging.info("OpenBudget bot ishga tushmoqda...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
