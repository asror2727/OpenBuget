# OpenBudget Telegram Bot

## GitHub
Ushbu loyihada token kod ichiga yozilmagan. GitHub'ga tokenni yuklamang.

Fayllar:
- bot.py
- requirements.txt
- render.yaml
- .env.example

## Render
Environment Variables:
BOT_TOKEN = BotFather'dan olingan token
ADMIN_ID = admin Telegram ID

Build Command:
pip install -r requirements.txt

Start Command:
python bot.py

## Muhim
SQLite fayli (`openbudget_bot.db`) Render Worker qayta ishga tushganda doimiy saqlash uchun yetarli emas. Ishlab chiqarish uchun PostgreSQL yoki boshqa persistent database ishlatish tavsiya qilinadi.
