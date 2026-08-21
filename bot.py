import asyncio, logging, os, re, sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN=os.getenv('BOT_TOKEN'); ADMIN_ID=int(os.getenv('ADMIN_ID','0'))
if not TOKEN: raise RuntimeError('BOT_TOKEN topilmadi')
logging.basicConfig(level=logging.INFO)
bot=Bot(TOKEN); dp=Dispatcher(storage=MemoryStorage())
conn=sqlite3.connect('openbudget_bot.db',check_same_thread=False); cur=conn.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY,balance INTEGER DEFAULT 0,referrer_id INTEGER,phone TEXT,is_banned INTEGER DEFAULT 0)')
cur.execute('CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,link TEXT,reward INTEGER DEFAULT 0)')
cur.execute('CREATE TABLE IF NOT EXISTS withdrawals(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,amount INTEGER,card_number TEXT,status TEXT DEFAULT "pending")')
cur.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)'); conn.commit()
DEFAULT={'start_text':'Assalomu alaykum! 💠 OpenBudget botiga xush kelibsiz.\n\nKerakli bo\'limni menyudan tanlang 👇','not_started':'⏳ Ovoz berish hali boshlanmadi.','ref_reward':'1000','vote_reward':'5000','min_withdraw':'10000','proof_channel':'','start_photo':'','start_caption':''}
def setting(k):
    cur.execute('SELECT value FROM settings WHERE key=?',(k,)); r=cur.fetchone(); return r[0] if r else DEFAULT.get(k,'')
def save_setting(k,v): cur.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,str(v))); conn.commit()
for k,v in DEFAULT.items():
    if cur.execute('SELECT 1 FROM settings WHERE key=?',(k,)).fetchone() is None: save_setting(k,v)
def admin(uid): return uid==ADMIN_ID
def main_kb(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='💠 Ovoz berish')],[KeyboardButton(text='💵 Balansim'),KeyboardButton(text='👑 Pul yechish')],[KeyboardButton(text='👥 Referal'),KeyboardButton(text='🌐 To\'lovlar tarixi')],[KeyboardButton(text='📊 Top 10')]],resize_keyboard=True)
def admin_kb(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='➕ Loyiha qo\'shish'),KeyboardButton(text='⚙️ Sozlamalar')],[KeyboardButton(text='📢 Isbot kanal'),KeyboardButton(text='💳 Pul yechish so\'rovlari')],[KeyboardButton(text='📊 Statistika'),KeyboardButton(text='❌ Menuga qaytish')]],resize_keyboard=True)
class U(StatesGroup): phone=State(); card=State(); card_confirm=State(); amount=State()
class A(StatesGroup): title=State(); link=State(); reward=State(); setting=State(); proof=State()
def phone_norm(s):
    s=re.sub(r'[^\d+]','',s.strip())
    if s.startswith('+998') and len(s)==13 and s[1:].isdigit(): return s
    if s.startswith('998') and len(s)==12 and s.isdigit(): return '+'+s
    if len(s)==9 and s.isdigit(): return '+998'+s
def card_norm(s):
    d=re.sub(r'\D','',s); return d if len(d)==16 else None

@dp.message(CommandStart())
async def start(m:types.Message):
    uid=m.from_user.id; p=m.text.split(maxsplit=1); ref=int(p[1]) if len(p)==2 and p[1].isdigit() and int(p[1])!=uid else None
    if not cur.execute('SELECT 1 FROM users WHERE user_id=?',(uid,)).fetchone():
        cur.execute('INSERT INTO users(user_id,referrer_id) VALUES(?,?)',(uid,ref));
        if ref: cur.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(int(setting('ref_reward')),ref))
        conn.commit()
    photo=setting('start_photo'); text=setting('start_caption') or setting('start_text')
    if photo:
        try: await m.answer_photo(photo,caption=text,reply_markup=main_kb()); return
        except: pass
    await m.answer(setting('start_text'),reply_markup=main_kb())

@dp.message(F.text=='💵 Balansim')
async def bal(m):
    r=cur.execute('SELECT balance FROM users WHERE user_id=?',(m.from_user.id,)).fetchone(); await m.answer(f"💰 Balansingiz: {r[0] if r else 0:,} so'm".replace(',',' '))
@dp.message(F.text=='👥 Referal')
async def ref(m):
    me=await bot.get_me(); n=cur.execute('SELECT COUNT(*) FROM users WHERE referrer_id=?',(m.from_user.id,)).fetchone()[0]
    await m.answer(f"👥 Referal havolangiz:\nhttps://t.me/{me.username}?start={m.from_user.id}\n\n👤 Takliflar: {n} ta\n🎁 Har biri: {int(setting('ref_reward')):,} so'm".replace(',',' '))
@dp.message(F.text=='💠 Ovoz berish')
async def vote(m,state:FSMContext):
    if cur.execute('SELECT COUNT(*) FROM projects').fetchone()[0]==0: await m.answer(setting('not_started')); return
    kb=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='📱 Telefon raqamni ulashish',request_contact=True)],[KeyboardButton(text='✍️ Raqamni qo\'lda kiritish')],[KeyboardButton(text='⬅️ Orqaga')]],resize_keyboard=True)
    await m.answer('📞 Ovoz berish uchun telefon raqamingizni yuboring:\n\nTelefon raqami +998991234567 yoki 991234567 formatida kiritilishi kerak.',reply_markup=kb); await state.set_state(U.phone)
@dp.message(U.phone,F.contact)
async def contact(m,state):
    n=phone_norm(m.contact.phone_number)
    if not n: await m.answer('❌ Raqam noto\'g\'ri.'); return
    await show_projects(m,n,state)
@dp.message(U.phone)
async def phone(m,state):
    if m.text=='⬅️ Orqaga': await state.clear(); await m.answer('Asosiy menyu.',reply_markup=main_kb()); return
    if m.text=='✍️ Raqamni qo\'lda kiritish': await m.answer('📞 Raqamni yuboring: +998991234567 yoki 991234567'); return
    n=phone_norm(m.text or '')
    if not n: await m.answer('❌ Raqam noto\'g\'ri. Misol: +998991234567 yoki 991234567'); return
    await show_projects(m,n,state)
async def show_projects(m,n,state):
    cur.execute('UPDATE users SET phone=? WHERE user_id=?',(n,m.from_user.id)); conn.commit(); await state.clear()
    rows=cur.execute('SELECT title,link,reward FROM projects ORDER BY id').fetchall(); text=f'📞 Raqamingiz: {n}\n\n📋 Ovoz berish loyihalari:\n\n'; kb=[]
    for i,(title,link,reward) in enumerate(rows):
        amount=reward or int(setting('vote_reward')); text+=f'🎯 {title}\n💰 Mukofot: {amount:,} so\'m\n\n'.replace(',',' '); kb.append([InlineKeyboardButton(text=f'🔗 {title}',url=link)]); kb.append([InlineKeyboardButton(text='✅ Ovoz berdim',callback_data=f'voted_{i}')])
    await m.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)); await m.answer('⚠️ Ovoz tekshiruvi va mukofot berish admin tomonidan qo\'lda amalga oshiriladi.',reply_markup=main_kb())
@dp.callback_query(F.data.startswith('voted_'))
async def voted(c):
    phone=cur.execute('SELECT phone FROM users WHERE user_id=?',(c.from_user.id,)).fetchone(); await c.answer('Adminga yuborildi.',show_alert=True)
    try: await bot.send_message(ADMIN_ID,f'🗳 Ovoz berdim\n👤 User: {c.from_user.id}\n📞 Telefon: {phone[0] if phone else "yo\'q"}')
    except: pass

@dp.message(F.text=='👑 Pul yechish')
async def withdraw(m,state):
    bal=cur.execute('SELECT balance FROM users WHERE user_id=?',(m.from_user.id,)).fetchone()[0]; mn=int(setting('min_withdraw'))
    if bal<mn: await m.answer(f'❌ Minimal yechish: {mn:,} so\'m\n💰 Balans: {bal:,} so\'m'.replace(',',' ')); return
    await m.answer('⚠️ DIQQAT!\n\nKarta raqamingizni diqqat bilan kiriting. Noto\'g\'ri karta uchun admin javobgar emas.\n\n💳 16 xonali karta raqamini kiriting:',reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='⬅️ Orqaga')]],resize_keyboard=True)); await state.set_state(U.card)
@dp.message(U.card)
async def card(m,state):
    if m.text=='⬅️ Orqaga': await state.clear(); await m.answer('Asosiy menyu.',reply_markup=main_kb()); return
    c=card_norm(m.text or '')
    if not c: await m.answer('❌ Karta aynan 16 ta raqam bo\'lishi kerak.'); return
    await state.update_data(card=c); await m.answer(f'💳 Karta: {c[:4]} **** **** {c[-4:]}\n\nHaqiqatan ham shu kartaga pul yechib olasizmi?',reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='✅ Ha, yechib olaman')],[KeyboardButton(text='❌ Bekor qilish')]],resize_keyboard=True)); await state.set_state(U.card_confirm)
@dp.message(U.card_confirm)
async def card_confirm(m,state):
    if m.text=='❌ Bekor qilish': await state.clear(); await m.answer('❌ Bekor qilindi.',reply_markup=main_kb()); return
    if m.text!='✅ Ha, yechib olaman': await m.answer('Tugmadan foydalaning.'); return
    await m.answer(f"💰 Necha pul yechib olmoqchisiz?\nMinimal summa: {int(setting('min_withdraw')):,} so'm".replace(',',' ')); await state.set_state(U.amount)
@dp.message(U.amount)
async def amount(m,state):
    if m.text=='⬅️ Orqaga': await state.clear(); await m.answer('Asosiy menyu.',reply_markup=main_kb()); return
    if not (m.text or '').isdigit(): await m.answer('❌ Faqat raqam kiriting.'); return
    amount=int(m.text); mn=int(setting('min_withdraw')); bal=cur.execute('SELECT balance FROM users WHERE user_id=?',(m.from_user.id,)).fetchone()[0]
    if amount<mn: await m.answer(f'❌ Minimal summa {mn:,} so\'m'.replace(',',' ')); return
    if amount>bal: await m.answer(f'❌ Balans yetarli emas: {bal:,} so\'m'.replace(',',' ')); return
    d=await state.get_data(); cur.execute('UPDATE users SET balance=balance-? WHERE user_id=?',(amount,m.from_user.id)); cur.execute('INSERT INTO withdrawals(user_id,amount,card_number) VALUES(?,?,?)',(m.from_user.id,amount,d['card'])); rid=cur.lastrowid; conn.commit(); await state.clear(); await m.answer('✅ So\'rov adminga yuborildi.',reply_markup=main_kb()); await notify(rid)
async def notify(rid):
    uid,amount,card=cur.execute('SELECT user_id,amount,card_number FROM withdrawals WHERE id=?',(rid,)).fetchone(); kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Tasdiqlash',callback_data=f'pay_ok_{rid}'),InlineKeyboardButton(text='❌ Rad etish',callback_data=f'pay_no_{rid}')]]); await bot.send_message(ADMIN_ID,f'💳 Yangi so\'rov\n🆔 {rid}\n👤 {uid}\n💰 {amount:,} so\'m\n💳 `{card}`'.replace(',',' '),reply_markup=kb,parse_mode='Markdown')
@dp.message(F.text=='🌐 To\'lovlar tarixi')
async def hist(m):
    rows=cur.execute('SELECT amount,card_number,status FROM withdrawals WHERE user_id=? ORDER BY id DESC LIMIT 10',(m.from_user.id,)).fetchall(); await m.answer('📭 Hali so\'rov yo\'q.' if not rows else '\n'.join(f'💰 {a:,} so\'m | 💳 ****{c[-4:]} | {s}'.replace(',',' ') for a,c,s in rows))
@dp.message(F.text=='📊 Top 10')
async def top(m):
    rows=cur.execute('SELECT user_id,balance FROM users ORDER BY balance DESC LIMIT 10').fetchall(); await m.answer('🏆 Top 10:\n\n'+'\n'.join(f'{i}. `{u}` — {b:,} so\'m'.replace(',',' ') for i,(u,b) in enumerate(rows,1)),parse_mode='Markdown')

@dp.message(Command('admin'))
async def admin_panel(m):
    if admin(m.from_user.id): await m.answer('👑 Admin panel',reply_markup=admin_kb())
@dp.message(F.text=='❌ Menuga qaytish')
async def back(m):
    if admin(m.from_user.id): await m.answer('Asosiy menyu.',reply_markup=main_kb())
@dp.message(F.text=='➕ Loyiha qo\'shish')
async def addp(m,state):
    if not admin(m.from_user.id): return
    await m.answer('🎯 Loyiha nomi:'); await state.set_state(A.title)
@dp.message(A.title)
async def atitle(m,state): await state.update_data(title=m.text.strip()); await m.answer('🔗 Loyiha linki:'); await state.set_state(A.link)
@dp.message(A.link)
async def alink(m,state):
    if not (m.text or '').startswith(('http://','https://','tg://')): await m.answer('❌ Link noto\'g\'ri.'); return
    await state.update_data(link=m.text.strip()); await m.answer(f'💰 Mukofot summasi (0 = global {int(setting("vote_reward")):,} so\'m):'.replace(',',' ')); await state.set_state(A.reward)
@dp.message(A.reward)
async def areward(m,state):
    if not (m.text or '').isdigit(): await m.answer('Faqat raqam.'); return
    d=await state.get_data(); cur.execute('INSERT INTO projects(title,link,reward) VALUES(?,?,?)',(d['title'],d['link'],int(m.text))); conn.commit(); await state.clear(); await m.answer('✅ Loyiha saqlandi va hammaga chiqadi.',reply_markup=admin_kb())

SET={'start_text':'🟢 Start matni','not_started':'⏳ Loyiha yo\'q matni','ref_reward':'👥 Referal summasi','vote_reward':'🗳 Ovoz mukofoti','min_withdraw':'💳 Minimal yechish','start_photo':'🖼 Start rasmi','start_caption':'✍️ Start caption'}
@dp.message(F.text=='⚙️ Sozlamalar')
async def settings(m):
    if not admin(m.from_user.id): return
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=v,callback_data='set_'+k)] for k,v in SET.items()]); await m.answer('⚙️ Sozlamalar:',reply_markup=kb)
@dp.callback_query(F.data.startswith('set_'))
async def set_start(c,state):
    if not admin(c.from_user.id): return
    k=c.data[4:]; await state.update_data(key=k); await c.message.answer('🖊 Qiymatni yuboring.' if k!='start_photo' else '🖼 Rasm yuboring.'); await state.set_state(A.setting); await c.answer()
@dp.message(A.setting)
async def save_set(m,state):
    d=await state.get_data(); k=d['key']; v=m.photo[-1].file_id if k=='start_photo' and m.photo else (m.text or '').strip()
    if k in ('ref_reward','vote_reward','min_withdraw') and not v.isdigit(): await m.answer('❌ Faqat raqam.'); return
    if not v: await m.answer('❌ Qiymat yuboring.'); return
    save_setting(k,v); await state.clear(); await m.answer('✅ Saqlandi.',reply_markup=admin_kb())
@dp.message(F.text=='📢 Isbot kanal')
async def proof(m,state):
    if not admin(m.from_user.id): return
    await m.answer('📢 @username yoki chat ID yuboring. O\'chirish uchun off:'); await state.set_state(A.proof)
@dp.message(A.proof)
async def save_proof(m,state): save_setting('proof_channel','' if m.text.lower()=='off' else m.text.strip()); await state.clear(); await m.answer('✅ Isbot kanali saqlandi.',reply_markup=admin_kb())
@dp.message(F.text=='📊 Statistika')
async def stats(m):
    if not admin(m.from_user.id): return
    u=cur.execute('SELECT COUNT(*) FROM users').fetchone()[0]; b=cur.execute('SELECT COALESCE(SUM(balance),0) FROM users').fetchone()[0]; p=cur.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'").fetchone()[0]; await m.answer(f'📊 Users: {u}\n💰 Jami balans: {b:,} so\'m\n💳 Pending: {p}'.replace(',',' '))
@dp.message(F.text=='💳 Pul yechish so\'rovlari')
async def requests(m):
    if not admin(m.from_user.id): return
    rows=cur.execute("SELECT id,user_id,amount,card_number FROM withdrawals WHERE status='pending'").fetchall()
    if not rows: await m.answer('📭 So\'rovlar yo\'q.'); return
    for rid,uid,a,c in rows:
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Tasdiqlash',callback_data=f'pay_ok_{rid}'),InlineKeyboardButton(text='❌ Rad etish',callback_data=f'pay_no_{rid}')]]); await m.answer(f'🆔 {rid}\n👤 {uid}\n💰 {a:,} so\'m\n💳 `{c}`'.replace(',',' '),reply_markup=kb,parse_mode='Markdown')
async def proof_send(rid,ok):
    ch=setting('proof_channel')
    if not ch:return
    uid,a,c=cur.execute('SELECT user_id,amount,card_number FROM withdrawals WHERE id=?',(rid,)).fetchone(); status='✅ TO\'LANDI' if ok else '❌ RAD ETILDI'
    try: await bot.send_message(ch,f'🧾 To\'lov isboti\n\n{status}\n👤 User ID: {uid}\n💰 {a:,} so\'m\n💳 Karta: **** **** **** {c[-4:]}'.replace(',',' '))
    except Exception as e: logging.error(e)
@dp.callback_query(F.data.startswith('pay_ok_'))
async def ok(c):
    if not admin(c.from_user.id): await c.answer('Ruxsat yo\'q',show_alert=True); return
    rid=int(c.data.split('_')[2]); row=cur.execute('SELECT user_id,amount,status FROM withdrawals WHERE id=?',(rid,)).fetchone()
    if not row or row[2]!='pending': await c.answer('Allaqachon ko\'rilgan.',show_alert=True); return
    cur.execute("UPDATE withdrawals SET status='approved' WHERE id=?",(rid,)); conn.commit(); await proof_send(rid,True); await c.message.edit_text(c.message.text+'\n\n✅ TASDIQLANDI'); await c.answer('Tasdiqlandi')
@dp.callback_query(F.data.startswith('pay_no_'))
async def no(c):
    if not admin(c.from_user.id): await c.answer('Ruxsat yo\'q',show_alert=True); return
    rid=int(c.data.split('_')[2]); row=cur.execute('SELECT user_id,amount,status FROM withdrawals WHERE id=?',(rid,)).fetchone()
    if not row or row[2]!='pending': await c.answer('Allaqachon ko\'rilgan.',show_alert=True); return
    uid,a,_=row; cur.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(a,uid)); cur.execute("UPDATE withdrawals SET status='rejected' WHERE id=?",(rid,)); conn.commit(); await proof_send(rid,False); await c.message.edit_text(c.message.text+'\n\n❌ RAD ETILDI, PUL QAYTARILDI'); await c.answer('Rad etildi')

async def main(): await dp.start_polling(bot)
if __name__=='__main__': asyncio.run(main())
