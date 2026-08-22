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

conn = sqlite3.connect(
    "openbudget_bot.db",
    check_same_thread=False
)

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
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT
)
""")

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


# =========================================================
# KEYBOARDS
# =========================================================

def main_keyboard():

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="💠 Ovoz berish")
            ],
            [
                KeyboardButton(text="💵 Balansim"),
                KeyboardButton(text="👥 Referal")
            ],
            [
                KeyboardButton(text="📊 Top 10"),
                KeyboardButton(text="⚙️ Sozlamalar")
            ]
        ],
        resize_keyboard=True
    )


def phone_keyboard():

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📱 Telefon raqamni yuborish",
                    request_contact=True
                )
            ],
            [
                KeyboardButton(text="⬅️ Orqaga")
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def admin_keyboard():

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="➕ Loyiha qo'shish"),
                KeyboardButton(text="📋 Loyihalar")
            ],
            [
                KeyboardButton(text="⛔ Loyihani to'xtatish"),
                KeyboardButton(text="▶️ Loyihani yoqish")
            ],
            [
                KeyboardButton(text="🗑 Loyiha o'chirish")
            ],
            [
                KeyboardButton(text="📢 Reklama yuborish"),
                KeyboardButton(text="📊 Statistika")
            ],
            [
                KeyboardButton(text="❌ Admin paneldan chiqish")
            ]
        ],
        resize_keyboard=True
    )


def back_keyboard():

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="⬅️ Orqaga")
            ]
        ],
        resize_keyboard=True
    )


# =========================================================
# HELPERS
# =========================================================

def is_admin(user_id):

    return user_id == ADMIN_ID


async def add_user(user_id):

    cursor.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user_id,)
    )

    user = cursor.fetchone()

    if not user:

        cursor.execute(
            """
            INSERT INTO users
            (user_id, balance, is_banned, advertising)
            VALUES (?, 0, 0, 1)
            """,
            (user_id,)
        )

        conn.commit()

        return True

    return False


def normalize_phone(phone):

    phone = phone.replace(" ", "")
    phone = phone.replace("-", "")
    phone = phone.replace("(", "")
    phone = phone.replace(")", "")

    if phone.startswith("+998"):
        if len(phone) == 13 and phone[1:].isdigit():
            return phone

    if phone.startswith("998"):
        if len(phone) == 12 and phone.isdigit():
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

    is_new = await add_user(user_id)

    welcome = (
        "Assalomu alaykum! 👋\n\n"
        "💠 OpenBudget botiga xush kelibsiz!\n\n"
        "Kerakli bo'limni tanlang 👇"
    )

    await message.answer(
        welcome,
        reply_markup=main_keyboard()
    )


# =========================================================
# BACK
# =========================================================

@dp.message(F.text == "⬅️ Orqaga")
async def back_handler(message: types.Message, state: FSMContext):

    await state.clear()

    if is_admin(message.from_user.id):
        await message.answer(
            "Admin panel.",
            reply_markup=admin_keyboard()
        )
    else:
        await message.answer(
            "Asosiy menyu.",
            reply_markup=main_keyboard()
        )


# =========================================================
# BALANCE
# =========================================================

@dp.message(F.text == "💵 Balansim")
async def balance_handler(message: types.Message):

    cursor.execute(
        "SELECT balance FROM users WHERE user_id = ?",
        (message.from_user.id,)
    )

    row = cursor.fetchone()

    balance = row[0] if row else 0

    await message.answer(
        f"💰 Balansingiz: {balance:,} so'm"
    )


# =========================================================
# REFERRAL
# =========================================================

@dp.message(F.text == "👥 Referal")
async def referral_handler(message: types.Message):

    me = await bot.get_me()

    link = (
        f"https://t.me/{me.username}"
        f"?start={message.from_user.id}"
    )

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE referrer_id = ?
        """,
        (message.from_user.id,)
    )

    count = cursor.fetchone()[0]

    await message.answer(
        "👥 Referal tizimi\n\n"
        f"🔗 Sizning havolangiz:\n{link}\n\n"
        f"👤 Taklif qilganlaringiz: {count} ta"
    )


# =========================================================
# VOICE / PROJECTS
# =========================================================

@dp.message(F.text == "💠 Ovoz berish")
async def voting_start(message: types.Message, state: FSMContext):

    cursor.execute(
        """
        SELECT id, title, link
        FROM projects
        WHERE is_active = 1
        ORDER BY id DESC
        """
    )

    projects = cursor.fetchall()

    if not projects:

        await message.answer(
            "⏳ Hozircha ovoz berish boshlanmagan.\n\n"
            "Faol loyihalar paydo bo'lganda shu yerda ko'rinadi."
        )

        return

    await state.set_state(UserStates.waiting_phone)

    await message.answer(
        "📞 Ovoz berish uchun telefon raqamingizni yuboring.\n\n"
        "Raqam quyidagi formatlardan birida bo'lishi mumkin:\n"
        "+998991234567\n"
        "991234567",
        reply_markup=phone_keyboard()
    )


# =========================================================
# CONTACT
# =========================================================

@dp.message(
    UserStates.waiting_phone,
    F.contact
)
async def phone_contact_handler(
    message: types.Message,
    state: FSMContext
):

    phone = message.contact.phone_number

    phone = normalize_phone(phone)

    if not phone:

        await message.answer(
            "❌ Telefon raqami noto'g'ri."
        )

        return

    await save_phone_and_show_projects(
        message,
        phone,
        state
    )


# =========================================================
# PHONE TEXT
# =========================================================

@dp.message(
    UserStates.waiting_phone,
    F.text
)
async def phone_text_handler(
    message: types.Message,
    state: FSMContext
):

    if message.text == "⬅️ Orqaga":

        await state.clear()

        await message.answer(
            "Asosiy menyu.",
            reply_markup=main_keyboard()
        )

        return

    phone = normalize_phone(message.text)

    if not phone:

        await message.answer(
            "❌ Raqam noto'g'ri.\n\n"
            "Masalan:\n"
            "+998991234567\n"
            "yoki\n"
            "991234567"
        )

        return

    await save_phone_and_show_projects(
        message,
        phone,
        state
    )


# =========================================================
# SAVE PHONE + PROJECTS
# =========================================================

async def save_phone_and_show_projects(
    message,
    phone,
    state
):

    cursor.execute(
        """
        UPDATE users
        SET phone = ?
        WHERE user_id = ?
        """,
        (
            phone,
            message.from_user.id
        )
    )

    conn.commit()

    cursor.execute(
        """
        SELECT id, title, link
        FROM projects
        WHERE is_active = 1
        ORDER BY id DESC
        """
    )

    projects = cursor.fetchall()

    text = (
        f"📞 Raqamingiz: {phone}\n\n"
        "📋 Ovoz berish loyihalari:\n\n"
    )

    buttons = []

    for project_id, title, link in projects:

        text += (
            f"🎯 {title}\n"
            f"🔗 Ovoz berish havolasi\n\n"
        )

        buttons.append([
            InlineKeyboardButton(
                text=f"🎯 {title}",
                url=link
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="📸 Ovoz berdim — screenshot yuborish",
            callback_data="send_screenshot"
        )
    ])

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

    await message.answer(
        text,
        reply_markup=keyboard
    )


# =========================================================
# SCREENSHOT BUTTON
# =========================================================

@dp.callback_query(F.data == "send_screenshot")
async def screenshot_start(
    call: types.CallbackQuery,
    state: FSMContext
):

    await state.set_state(
        UserStates.waiting_screenshot
    )

    await call.message.answer(
        "📸 Ovoz berganingizni tasdiqlovchi "
        "screenshotni yuboring.\n\n"
        "Screenshot admin tomonidan ko'rib chiqiladi."
    )

    await call.answer()


# =========================================================
# SCREENSHOT RECEIVE
# =========================================================

@dp.message(
    UserStates.waiting_screenshot,
    F.photo
)
async def receive_screenshot(
    message: types.Message,
    state: FSMContext
):

    user_id = message.from_user.id

    cursor.execute(
        """
        SELECT phone
        FROM users
        WHERE user_id = ?
        """,
        (user_id,)
    )

    row = cursor.fetchone()

    phone = row[0] if row else "Noma'lum"

    cursor.execute(
        """
        SELECT title
        FROM projects
        WHERE is_active = 1
        ORDER BY id DESC
        """
    )

    project_rows = cursor.fetchall()

    project_text = ", ".join(
        [x[0] for x in project_rows]
    )

    caption = (
        "📸 Yangi ovoz screenshot\n\n"
        f"👤 User ID: {user_id}\n"
        f"📞 Telefon: {phone}\n"
        f"🎯 Faol loyihalar: {project_text or 'Yo‘q'}\n\n"
        "⚠️ Bu xabar faqat admin ko'rib chiqishi uchun."
    )

    photo_id = message.photo[-1].file_id

    await bot.send_photo(
        ADMIN_ID,
        photo=photo_id,
        caption=caption
    )

    await message.answer(
        "✅ Screenshot adminga yuborildi.\n\n"
        "Admin tomonidan ko'rib chiqiladi.",
        reply_markup=main_keyboard()
    )

    await state.clear()


# =========================================================
# WRONG SCREENSHOT
# =========================================================

@dp.message(
    UserStates.waiting_screenshot
)
async def wrong_screenshot(
    message: types.Message
):

    await message.answer(
        "📸 Iltimos, screenshotni rasm sifatida yuboring."
    )


# =========================================================
# ADMIN PANEL
# =========================================================

@dp.message(Command("admin"))
async def admin_command(message: types.Message):

    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "👑 ADMIN PANEL",
        reply_markup=admin_keyboard()
    )


# =========================================================
# ADMIN EXIT
# =========================================================

@dp.message(F.text == "❌ Admin paneldan chiqish")
async def admin_exit(message: types.Message):

    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "Asosiy menyu.",
        reply_markup=main_keyboard()
    )


# =========================================================
# ADD PROJECT
# =========================================================

@dp.message(F.text == "➕ Loyiha qo'shish")
async def add_project_start(
    message: types.Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        return

    await state.set_state(
        AdminStates.project_title
    )

    await message.answer(
        "🎯 Loyiha nomini yozing:",
        reply_markup=back_keyboard()
    )


@dp.message(AdminStates.project_title)
async def add_project_title(
    message: types.Message,
    state: FSMContext
):

    if message.text == "⬅️ Orqaga":

        await state.clear()

        await message.answer(
            "Admin panel.",
            reply_markup=admin_keyboard()
        )

        return

    await state.update_data(
        title=message.text.strip()
    )

    await state.set_state(
        AdminStates.project_link
    )

    await message.answer(
        "🔗 Endi loyiha linkini yuboring:"
    )


@dp.message(AdminStates.project_link)
async def add_project_link(
    message: types.Message,
    state: FSMContext
):

    if message.text == "⬅️ Orqaga":

        await state.clear()

        await message.answer(
            "Admin panel.",
            reply_markup=admin_keyboard()
        )

        return

    link = message.text.strip()

    if not link.startswith(
        ("http://", "https://", "tg://")
    ):

        await message.answer(
            "❌ Link noto'g'ri.\n"
            "https:// bilan boshlanadigan link yuboring."
        )

        return

    data = await state.get_data()

    cursor.execute(
        """
        INSERT INTO projects
        (title, link, is_active)
        VALUES (?, ?, 1)
        """,
        (
            data["title"],
            link
        )
    )

    conn.commit()

    await state.clear()

    await message.answer(
        "✅ Loyiha qo'shildi va hozir faol.",
        reply_markup=admin_keyboard()
    )


# =========================================================
# LIST PROJECTS
# =========================================================

@dp.message(F.text == "📋 Loyihalar")
async def admin_projects(message: types.Message):

    if not is_admin(message.from_user.id):
        return

    cursor.execute(
        """
        SELECT id, title, link, is_active
        FROM projects
        ORDER BY id DESC
        """
    )

    projects = cursor.fetchall()

    if not projects:

        await message.answer(
            "📭 Hozircha loyihalar yo'q."
        )

        return

    text = "📋 Loyihalar:\n\n"

    for pid, title, link, active in projects:

        status = (
            "🟢 FAOL"
            if active
            else "🔴 TO'XTATILGAN"
        )

        text += (
            f"🆔 {pid}\n"
            f"🎯 {title}\n"
            f"📌 {status}\n"
            f"🔗 {link}\n"
            "━━━━━━━━━━━━\n"
        )

    await message.answer(text)


# =========================================================
# STOP PROJECT
# =========================================================

@dp.message(F.text == "⛔ Loyihani to'xtatish")
async def stop_project(message: types.Message):

    if not is_admin(message.from_user.id):
        return

    cursor.execute(
        """
        SELECT id, title
        FROM projects
        WHERE is_active = 1
        """
    )

    projects = cursor.fetchall()

    if not projects:

        await message.answer(
            "🟢 Hozir faol loyiha yo'q."
        )

        return

    buttons = []

    for pid, title in projects:

        buttons.append([
            InlineKeyboardButton(
                text=f"⛔ {title}",
                callback_data=f"stop_project:{pid}"
            )
        ])

    await message.answer(
        "Qaysi loyihani to'xtatasiz?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )


@dp.callback_query(
    F.data.startswith("stop_project:")
)
async def stop_project_callback(
    call: types.CallbackQuery
):

    if not is_admin(call.from_user.id):
        return

    project_id = int(
        call.data.split(":")[1]
    )

    cursor.execute(
        """
        UPDATE projects
        SET is_active = 0
        WHERE id = ?
        """,
        (project_id,)
    )

    conn.commit()

    await call.message.edit_text(
        "⛔ Loyiha to'xtatildi."
    )

    await call.answer("To'xtatildi")


# =========================================================
# START PROJECT
# =========================================================

@dp.message(F.text == "▶️ Loyihani yoqish")
async def start_project(message: types.Message):

    if not is_admin(message.from_user.id):
        return

    cursor.execute(
        """
        SELECT id, title
        FROM projects
        WHERE is_active = 0
        """
    )

    projects = cursor.fetchall()

    if not projects:

        await message.answer(
            "🟢 To'xtatilgan loyiha yo'q."
        )

        return

    buttons = []

    for pid, title in projects:

        buttons.append([
            InlineKeyboardButton(
                text=f"▶️ {title}",
                callback_data=f"start_project:{pid}"
            )
        ])

    await message.answer(
        "Qaysi loyihani qayta yoqasiz?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )


@dp.callback_query(
    F.data.startswith("start_project:")
)
async def start_project_callback(
    call: types.CallbackQuery
):

    if not is_admin(call.from_user.id):
        return

    project_id = int(
        call.data.split(":")[1]
    )

    cursor.execute(
        """
        UPDATE projects
        SET is_active = 1
        WHERE id = ?
        """,
        (project_id,)
    )

    conn.commit()

    await call.message.edit_text(
        "▶️ Loyiha qayta yoqildi."
    )

    await call.answer("Yoqildi")


# =========================================================
# DELETE PROJECT
# =========================================================

@dp.message(F.text == "🗑 Loyiha o'chirish")
async def delete_project(message: types.Message):

    if not is_admin(message.from_user.id):
        return

    cursor.execute(
        """
        SELECT id, title
        FROM projects
        """
    )

    projects = cursor.fetchall()

    if not projects:

        await message.answer(
            "📭 Loyihalar yo'q."
        )

        return

    buttons = []

    for pid, title in projects:

        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {title}",
                callback_data=f"delete_project:{pid}"
            )
        ])

    await message.answer(
        "O'chiriladigan loyihani tanlang:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )


@dp.callback_query(
    F.data.startswith("delete_project:")
)
async def delete_project_callback(
    call: types.CallbackQuery
):

    if not is_admin(call.from_user.id):
        return

    project_id = int(
        call.data.split(":")[1]
    )

    cursor.execute(
        """
        DELETE FROM projects
        WHERE id = ?
        """,
        (project_id,)
    )

    conn.commit()

    await call.message.edit_text(
        "🗑 Loyiha o'chirildi."
    )

    await call.answer("O'chirildi")


# =========================================================
# STATISTICS
# =========================================================

@dp.message(F.text == "📊 Statistika")
async def statistics(message: types.Message):

    if not is_admin(message.from_user.id):
        return

    cursor.execute(
        "SELECT COUNT(*) FROM users"
    )

    users = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE phone IS NOT NULL
        AND phone != ''
        """
    )

    phones = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM projects
        WHERE is_active = 1
        """
    )

    active_projects = cursor.fetchone()[0]

    await message.answer(
        "📊 BOT STATISTIKASI\n\n"
        f"👥 Foydalanuvchilar: {users}\n"
        f"📞 Telefon kiritganlar: {phones}\n"
        f"🎯 Faol loyihalar: {active_projects}"
    )


# =========================================================
# ADVERTISING START
# =========================================================

@dp.message(F.text == "📢 Reklama yuborish")
async def broadcast_start(
    message: types.Message,
    state: FSMContext
):

    if not is_admin(message.from_user.id):
        return

    await state.set_state(
        AdminStates.broadcast_photo
    )

    await message.answer(
        "📸 Reklama uchun rasm yuboring.\n\n"
        "Agar rasm kerak bo'lmasa, /skip yozing.",
        reply_markup=back_keyboard()
    )


# =========================================================
# BROADCAST PHOTO
# =========================================================

@dp.message(AdminStates.broadcast_photo)
async def broadcast_photo(
    message: types.Message,
    state: FSMContext
):

    if message.text == "⬅️ Orqaga":

        await state.clear()

        await message.answer(
            "Admin panel.",
            reply_markup=admin_keyboard()
        )

        return

    if message.text == "/skip":

        await state.update_data(
            photo=None
        )

    elif message.photo:

        photo_id = message.photo[-1].file_id

        await state.update_data(
            photo=photo_id
        )

    else:

        await message.answer(
            "📸 Rasm yuboring yoki /skip yozing."
        )

        return

    await state.set_state(
        AdminStates.broadcast_text
    )

    await message.answer(
        "✍️ Endi reklama matnini yuboring:"
    )


# =========================================================
# BROADCAST TEXT
# =========================================================

@dp.message(AdminStates.broadcast_text)
async def broadcast_text(
    message: types.Message,
    state: FSMContext
):

    if message.text == "⬅️ Orqaga":

        await state.clear()

        await message.answer(
            "Admin panel.",
            reply_markup=admin_keyboard()
        )

        return

    text = message.text.strip()

    if not text:

        await message.answer(
            "❌ Matn bo'sh bo'lmasin."
        )

        return

    data = await state.get_data()

    photo = data.get("photo")

    await state.clear()

    cursor.execute(
        """
        SELECT user_id
        FROM users
        WHERE is_banned = 0
        AND advertising = 1
        """
    )

    users = cursor.fetchall()

    success = 0
    failed = 0

    await message.answer(
        f"📢 Reklama {len(users)} ta foydalanuvchiga yuborilmoqda..."
    )

    for (user_id,) in users:

        try:

            if photo:

                await bot.send_photo(
                    user_id,
                    photo=photo,
                    caption=text
                )

            else:

                await bot.send_message(
                    user_id,
                    text
                )

            success += 1

            await asyncio.sleep(0.05)

        except Exception:

            failed += 1

    await message.answer(
        "📢 Reklama tugadi!\n\n"
        f"✅ Yuborildi: {success}\n"
        f"❌ Yuborilmadi: {failed}",
        reply_markup=admin_keyboard()
    )


# =========================================================
# ADVERTISING SETTINGS
# =========================================================

@dp.message(F.text == "⚙️ Sozlamalar")
async def user_settings(message: types.Message):

    cursor.execute(
        """
        SELECT advertising
        FROM users
        WHERE user_id = ?
        """,
        (message.from_user.id,)
    )

    row = cursor.fetchone()

    advertising = row[0] if row else 1

    status = (
        "🟢 Yoqilgan"
        if advertising
        else "🔴 O'chirilgan"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Reklamani o'zgartirish",
                    callback_data="toggle_ads"
                )
            ]
        ]
    )

    await message.answer(
        "⚙️ Sozlamalar\n\n"
        f"📢 Reklama xabarlari: {status}",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "toggle_ads")
async def toggle_ads(call: types.CallbackQuery):

    cursor.execute(
        """
        SELECT advertising
        FROM users
        WHERE user_id = ?
        """,
        (call.from_user.id,)
    )

    row = cursor.fetchone()

    current = row[0] if row else 1

    new_value = 0 if current else 1

    cursor.execute(
        """
        UPDATE users
        SET advertising = ?
        WHERE user_id = ?
        """,
        (
            new_value,
            call.from_user.id
        )
    )

    conn.commit()

    status = (
        "🟢 Yoqildi"
        if new_value
        else "🔴 O'chirildi"
    )

    await call.message.edit_text(
        f"📢 Reklama xabarlari: {status}"
    )

    await call.answer()


# =========================================================
# TOP 10
# =========================================================

@dp.message(F.text == "📊 Top 10")
async def top_users(message: types.Message):

    cursor.execute(
        """
        SELECT user_id, balance
        FROM users
        ORDER BY balance DESC
        LIMIT 10
        """
    )

    rows = cursor.fetchall()

    text = "🏆 TOP 10\n\n"

    for index, (uid, balance) in enumerate(rows, 1):

        text += (
            f"{index}. `{uid}` — "
            f"{balance:,} so'm\n"
        )

    await message.answer(
        text,
        parse_mode="Markdown"
    )


# =========================================================
# RUN
# =========================================================

async def main():

    logging.info(
        "OpenBudget bot ishga tushdi..."
    )

    await dp.start_polling(bot)


if __name__ == "__main__":

    asyncio.run(main())
