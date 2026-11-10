import os, time, json, hmac, hashlib, asyncio, logging, pathlib
from datetime import datetime, timezone
from urllib.parse import parse_qsl
from aiohttp import web, ClientSession, ClientTimeout, WSMsgType
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
                           Message, WebAppInfo, BotCommand)
from dotenv import load_dotenv
load_dotenv()
import db, engine

BOT_TOKEN = os.environ["BOT_TOKEN"]
TD_KEY = os.environ["TWELVE_API_KEY"]
CHANNEL = os.environ.get("CHANNEL_USERNAME", "@your_channel")
WEBAPP_URL = os.environ["WEBAPP_URL"].strip().rstrip("/")
if not WEBAPP_URL.startswith("https://"):
    WEBAPP_URL = "https://" + WEBAPP_URL.removeprefix("http://")
PORT = int(os.environ.get("PORT", 8080))
ADMINS = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x}
POSTBACK_SECRET = os.environ.get("POSTBACK_SECRET", "")
POSTBACK_REQUIRED = os.environ.get("POSTBACK_REQUIRED", "0") == "1"
SUBID = os.environ.get("REG_SUBID_PARAM", "").strip()
DEV_MODE = os.environ.get("DEV_MODE", "0") == "1"
TD_WS = os.environ.get("TD_WS", "0") == "1"          # платный тариф Twelve Data с WebSocket
REPORT_HOUR = int(os.environ.get("REPORT_HOUR_UTC", 16))  # 16 UTC = 21:00 по GMT+5
REG_LINK = "https://pocket-friends.co/r/a2lx2ihvqq"
PROMO = "FRIENDA2LX2IHVQQ"
PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "BTC/USD", "ETH/USD"]
TFSEC = {"1min": 60, "5min": 300, "15min": 900}
ALL_PAIRS = PAIRS + engine.OTC_PAIRS
OTC_LIVE = False
BASE = pathlib.Path(__file__).parent
LIVE: dict = {}
OWNER = os.environ.get("OWNER_USERNAME", "").lstrip("@")
PRO_STARS = int(os.environ.get("PRO_PRICE_STARS", 250))
PRO_USDT = float(os.environ.get("PRO_PRICE_USDT", 5))
PRO_DAYS = int(os.environ.get("PRO_DAYS", 30))
FREE_SIGNALS = db.FREE_SIGNALS
REF_BONUS = int(os.environ.get("REF_BONUS", 2))
PRO_DAILY_CAP = int(os.environ.get("PRO_DAILY_CAP", 300))
CB_TOKEN = os.environ.get("CRYPTOBOT_TOKEN", "").strip()
CB_API = "https://testnet-pay.crypt.bot/api" if os.environ.get("CRYPTOBOT_TESTNET", "0") == "1" else "https://pay.crypt.bot/api"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
def kb(*rows): return InlineKeyboardMarkup(inline_keyboard=list(rows))
def btn(t, **k): return InlineKeyboardButton(text=t, **k)
def reg_link(uid):
    if not SUBID: return REG_LINK
    return REG_LINK + ("&" if "?" in REG_LINK else "?") + f"{SUBID}={uid}"
def fmt(pair, x): return f"{x:.{3 if 'JPY' in pair else 2 if pair[:3] in ('BTC', 'ETH') else 5}f}"

# ───────────── ТЕКСТЫ БОТА (ru / uz / en) ─────────────
B = {
"ru": dict(
  choose="🌐 Выберите язык", welcome="⚡ <b>QUICK AI</b>\n\nТехнический анализ рынка в реальном времени.\n\nШаг 1. Подпишись на наш канал, затем нажми «Проверить».",
  sub="📢 Подписаться", chk="✅ Проверить подписку", subfail="Сначала подпишись на канал",
  step2="Шаг 2. Регистрация в Pocket Option.\n\nРегистрируйся строго по кнопке ниже и введи промокод:\n<code>{promo}</code>\n\nУже зарегистрирован через нашу ссылку? Нажми «Далее».",
  reg="🚀 Регистрация", nxt="Далее ➜",
  step3="Шаг 3. Пополни счёт.\n\nМинимум — <b>$10</b>.\nСовет: чтобы управлять рисками и не ставить весь баланс в одну сделку, лучше начинать с <b>$50–100</b> и ставить не больше 1–5% на сделку.\n\nПосле пополнения вернись и нажми кнопку.",
  dep="💳 Депозит готов", wait="⏳ Ждём подтверждение депозита от Pocket Option. Обычно это занимает несколько минут, бот сам пришлёт доступ.",
  granted="🎉 Доступ открыт!\n\nОткрывай терминал QUICK AI: сигналы, графики и подсказки по входу и выходу внутри.",
  back="С возвращением! Терминал QUICK AI ждёт вас.", open="⚡ Открыть QUICK AI", openq="Открывай терминал:",
  need="Сначала пройди шаги в /start: подписка, регистрация и депозит.",
  invite="👥 Приглашай друзей и получай +2 сигнала в день за каждого, кто пополнил счёт (максимум +10).\n\nТвоя ссылка:\n{link}\n\nПриглашено: {n}, пополнили счёт: {d}",
  bonus="🎁 Ваш друг пополнил счёт. Вам +2 сигнала в день (максимум +10).",
  W="✅ Сделка закрыта в плюс", L="❌ Сделка закрыта в минус", D="➖ Цена не изменилась", X="Результат недоступен", min="мин"),
"uz": dict(
  choose="🌐 Tilni tanlang", welcome="⚡ <b>QUICK AI</b>\n\nBozorning real vaqtdagi texnik tahlili.\n\n1-qadam. Kanalimizga obuna bo'ling, so'ng «Tekshirish» tugmasini bosing.",
  sub="📢 Obuna bo'lish", chk="✅ Obunani tekshirish", subfail="Avval kanalga obuna bo'ling",
  step2="2-qadam. Pocket Option'da ro'yxatdan o'tish.\n\nFaqat quyidagi tugma orqali ro'yxatdan o'ting va promokodni kiriting:\n<code>{promo}</code>\n\nAllaqachon bizning havola orqali ro'yxatdan o'tganmisiz? «Keyingi» tugmasini bosing.",
  reg="🚀 Ro'yxatdan o'tish", nxt="Keyingi ➜",
  step3="3-qadam. Hisobni to'ldiring.\n\nMinimal summa — <b>$10</b>.\nMaslahat: xavfni boshqarish va butun balansni bitta bitimga tikmaslik uchun <b>$50–100</b> dan boshlang va bitimga 1–5% dan ko'p tikmang.\n\nHisobni to'ldirgach, qaytib kelib tugmani bosing.",
  dep="💳 Depozit tayyor", wait="⏳ Pocket Option depozitni tasdiqlashini kutmoqdamiz. Odatda bir necha daqiqa oladi, bot o'zi kirishni yuboradi.",
  granted="🎉 Kirish ochildi!\n\nQUICK AI terminalini oching: signallar, grafiklar va kirish-chiqish bo'yicha maslahatlar ichida.",
  back="Xush kelibsiz! QUICK AI terminali sizni kutmoqda.", open="⚡ QUICK AI ni ochish", openq="Terminalni oching:",
  need="Avval /start dagi qadamlarni bajaring: obuna, ro'yxatdan o'tish va depozit.",
  invite="👥 Do'stlaringizni taklif qiling: hisobini to'ldirgan har bir do'st uchun kuniga +2 signal (maksimum +10).\n\nSizning havolangiz:\n{link}\n\nTaklif qilingan: {n}, hisobini to'ldirgan: {d}",
  bonus="🎁 Do'stingiz hisobini to'ldirdi. Sizga kuniga +2 signal (maksimum +10).",
  W="✅ Bitim foydada yopildi", L="❌ Bitim zararda yopildi", D="➖ Narx o'zgarmadi", X="Natija mavjud emas", min="daq"),
"en": dict(
  choose="🌐 Choose your language", welcome="⚡ <b>QUICK AI</b>\n\nReal-time technical market analysis.\n\nStep 1. Subscribe to our channel, then tap “Check”.",
  sub="📢 Subscribe", chk="✅ Check subscription", subfail="Please subscribe to the channel first",
  step2="Step 2. Register at Pocket Option.\n\nRegister strictly via the button below and enter the promo code:\n<code>{promo}</code>\n\nAlready registered via our link? Tap “Next”.",
  reg="🚀 Register", nxt="Next ➜",
  step3="Step 3. Fund your account.\n\nMinimum — <b>$10</b>.\nTip: to manage risk and avoid putting your whole balance into one trade, start with <b>$50–100</b> and risk no more than 1–5% per trade.\n\nAfter funding, come back and tap the button.",
  dep="💳 Deposit done", wait="⏳ Waiting for Pocket Option to confirm the deposit. It usually takes a few minutes, the bot will send access automatically.",
  granted="🎉 Access granted!\n\nOpen the QUICK AI terminal: signals, charts and entry/exit hints inside.",
  back="Welcome back! The QUICK AI terminal is waiting.", open="⚡ Open QUICK AI", openq="Open the terminal:",
  need="First complete the steps in /start: subscription, registration and deposit.",
  invite="👥 Invite friends and get +2 signals per day for each one who funds their account (up to +10).\n\nYour link:\n{link}\n\nInvited: {n}, funded: {d}",
  bonus="🎁 Your friend funded their account. You get +2 signals per day (up to +10).",
  W="✅ Trade closed in profit", L="❌ Trade closed in loss", D="➖ Price did not change", X="Result unavailable", min="min"),
}
B["ru"].update(
  invite="👥 Приглашай друзей: за каждого, кто пополнил счёт, ты получаешь +{ref} сигнала.\n\nТвоя ссылка:\n{link}\n\nПриглашено: {n}, с доступом: {d}",
  bonus="🎁 Ваш друг присоединился. Вам +{n} сигнала.", free_note="🎁 Вам начислено {n} бесплатных сигналов.",
  pro_title="👑 <b>QUICK AI Pro</b>\n\nБезлимитные сигналы на {days} дней.\nСтоимость: {stars} ⭐ или {usdt} USDT.\n\nБесплатно: {free} сигналов после регистрации и +{ref} за каждого приглашённого друга.",
  btn_stars="⭐ Оплатить Telegram Stars", btn_crypto="💎 Оплатить через CryptoBot",
  stars_text="⭐ <b>Оплата звёздами</b>\n\n1. Откройте чат с владельцем.\n2. Отправьте подарки на сумму <b>{stars} ⭐</b>.\n3. Пришлите свой ID: <code>{uid}</code>\n\nПосле проверки Pro включится на {days} дней.",
  btn_dm="💬 Написать владельцу", btn_sent="✅ Я отправил подарки",
  stars_wait="⏳ Заявка отправлена. Как только владелец проверит подарки, Pro включится.", stars_no="Заявка не подтверждена. Если вы отправили подарки, напишите владельцу.",
  crypto_text="💎 <b>Оплата через CryptoBot</b>\n\nСумма: {usdt} USDT. Оплатите счёт, и Pro включится автоматически в течение минуты.", btn_pay="💳 Оплатить {usdt} USDT",
  crypto_off="Оплата через CryptoBot пока недоступна.", pro_on="👑 Pro включён до {date}. Безлимитные сигналы!",
  pro_soon="⏳ Ваш Pro заканчивается {date}. Продлите, чтобы не потерять безлимит.", pro_end="Срок Pro закончился. Продлите, чтобы снова получать безлимитные сигналы.")
B["uz"].update(
  invite="👥 Do'stlarni taklif qiling: hisobini to'ldirgan har bir do'st uchun +{ref} signal olasiz.\n\nSizning havolangiz:\n{link}\n\nTaklif qilingan: {n}, kirish ochilgan: {d}",
  bonus="🎁 Do'stingiz qo'shildi. Sizga +{n} signal.", free_note="🎁 Sizga {n} ta bepul signal berildi.",
  pro_title="👑 <b>QUICK AI Pro</b>\n\n{days} kunlik cheksiz signallar.\nNarxi: {stars} ⭐ yoki {usdt} USDT.\n\nBepul: ro'yxatdan keyin {free} ta signal va har bir taklif qilingan do'st uchun +{ref}.",
  btn_stars="⭐ Telegram Stars bilan to'lash", btn_crypto="💎 CryptoBot orqali to'lash",
  stars_text="⭐ <b>Yulduzlar bilan to'lov</b>\n\n1. Egasi bilan chatni oching.\n2. <b>{stars} ⭐</b> miqdorida sovg'alar yuboring.\n3. ID raqamingizni yuboring: <code>{uid}</code>\n\nTekshirilgandan so'ng Pro {days} kunga yoqiladi.",
  btn_dm="💬 Egasiga yozish", btn_sent="✅ Sovg'alarni yubordim",
  stars_wait="⏳ Ariza yuborildi. Ega sovg'alarni tekshirgach, Pro yoqiladi.", stars_no="Ariza tasdiqlanmadi. Sovg'a yuborgan bo'lsangiz, egasiga yozing.",
  crypto_text="💎 <b>CryptoBot orqali to'lov</b>\n\nSumma: {usdt} USDT. Hisobni to'lang, Pro bir daqiqa ichida avtomatik yoqiladi.", btn_pay="💳 {usdt} USDT to'lash",
  crypto_off="CryptoBot orqali to'lov hozircha mavjud emas.", pro_on="👑 Pro {date} gacha yoqildi. Cheksiz signallar!",
  pro_soon="⏳ Pro {date} da tugaydi. Cheksizlikni yo'qotmaslik uchun uzaytiring.", pro_end="Pro muddati tugadi. Cheksiz signallar uchun uzaytiring.")
B["en"].update(
  invite="👥 Invite friends: you get +{ref} signals for each one who funds their account.\n\nYour link:\n{link}\n\nInvited: {n}, with access: {d}",
  bonus="🎁 Your friend joined. You get +{n} signals.", free_note="🎁 You received {n} free signals.",
  pro_title="👑 <b>QUICK AI Pro</b>\n\nUnlimited signals for {days} days.\nPrice: {stars} ⭐ or {usdt} USDT.\n\nFree: {free} signals after registration and +{ref} for every invited friend.",
  btn_stars="⭐ Pay with Telegram Stars", btn_crypto="💎 Pay with CryptoBot",
  stars_text="⭐ <b>Pay with Stars</b>\n\n1. Open the chat with the owner.\n2. Send gifts worth <b>{stars} ⭐</b>.\n3. Send your ID: <code>{uid}</code>\n\nAfter verification Pro is enabled for {days} days.",
  btn_dm="💬 Message the owner", btn_sent="✅ I sent the gifts",
  stars_wait="⏳ Request sent. Pro will be enabled once the owner checks the gifts.", stars_no="Request not confirmed. If you sent gifts, message the owner.",
  crypto_text="💎 <b>Pay with CryptoBot</b>\n\nAmount: {usdt} USDT. Pay the invoice and Pro turns on automatically within a minute.", btn_pay="💳 Pay {usdt} USDT",
  crypto_off="CryptoBot payments are not available yet.", pro_on="👑 Pro is active until {date}. Unlimited signals!",
  pro_soon="⏳ Your Pro ends on {date}. Renew to keep unlimited signals.", pro_end="Your Pro has ended. Renew to get unlimited signals again.")
async def L(uid): return await db.get_lang(uid)
def bt(lang, key, **kw): return B.get(lang, B["ru"])[key].format(**kw)
def open_app(lang): return kb([btn(bt(lang, "open"), web_app=WebAppInfo(url=WEBAPP_URL))])
lang_kb = kb([btn("🇷🇺 Русский", callback_data="lang_ru"), btn("🇺🇿 O'zbekcha", callback_data="lang_uz"), btn("🇬🇧 English", callback_data="lang_en")])

def step1_kb(lang):
    return kb([btn(bt(lang, "sub"), url=f"https://t.me/{CHANNEL.lstrip('@')}")], [btn(bt(lang, "chk"), callback_data="check_sub")])

# ───────────── ВОРОНКА ─────────────
@dp.message(CommandStart())
async def start(m: Message, command: CommandObject):
    ref = pay = None
    if command.args and command.args.startswith("ref_"):
        try: ref = int(command.args[4:])
        except ValueError: pass
    elif command.args in ("pay_stars", "pay_crypto", "pro"): pay = command.args
    u = m.from_user
    await db.upsert_user(u.id, u.username, u.first_name, ref)
    usr = await db.get_user(u.id)
    if not usr.get("lang"):
        return await m.answer(bt("ru", "choose") + " / Tilni tanlang / Choose language", reply_markup=lang_kb)
    lang = usr["lang"]
    if pay and (usr["deposited"] or u.id in ADMINS):
        return await pay_dispatch(u.id, lang, pay)
    if usr["deposited"] or u.id in ADMINS:
        return await m.answer(bt(lang, "back"), reply_markup=open_app(lang))
    await m.answer(bt(lang, "welcome"), parse_mode="HTML", reply_markup=step1_kb(lang))

@dp.callback_query(F.data.startswith("lang_"))
async def pick_lang(c: CallbackQuery):
    lang = c.data[5:]
    if lang not in B: return await c.answer()
    await db.set_lang(c.from_user.id, lang); await c.answer()
    if await db.has_access(c.from_user.id) or c.from_user.id in ADMINS:
        await c.message.edit_text(bt(lang, "back"), reply_markup=open_app(lang))
    else:
        await c.message.edit_text(bt(lang, "welcome"), parse_mode="HTML", reply_markup=step1_kb(lang))

@dp.message(Command("lang"))
async def lang_cmd(m: Message): await m.answer("🌐", reply_markup=lang_kb)

@dp.callback_query(F.data == "check_sub")
async def check_sub(c: CallbackQuery):
    lang = await L(c.from_user.id)
    try:
        mem = await bot.get_chat_member(CHANNEL, c.from_user.id)
        ok = mem.status in ("member", "administrator", "creator")
    except Exception:
        ok = False
    if not ok: return await c.answer(bt(lang, "subfail"), show_alert=True)
    await db.set_flag(c.from_user.id, subscribed=1)
    await c.message.edit_text(bt(lang, "step2", promo=PROMO), parse_mode="HTML",
        reply_markup=kb([btn(bt(lang, "reg"), url=reg_link(c.from_user.id))], [btn(bt(lang, "nxt"), callback_data="to_deposit")]))

@dp.callback_query(F.data == "to_deposit")
async def to_deposit(c: CallbackQuery):
    lang = await L(c.from_user.id); await db.set_flag(c.from_user.id, registered=1)
    await c.message.edit_text(bt(lang, "step3"), parse_mode="HTML", reply_markup=kb([btn(bt(lang, "dep"), callback_data="dep_done")]))

async def grant_access(uid, amount=0.0):
    u = await db.get_user(uid)
    if u and u["deposited"]: return
    await db.set_flag(uid, deposited=1, deposit_sum=amount, deposit_at=int(time.time()))
    lang = (u or {}).get("lang") or "ru"
    given = await db.give_free(uid)
    text = bt(lang, "granted") + (("\n\n" + bt(lang, "free_note", n=FREE_SIGNALS)) if given else "")
    try: await bot.send_message(uid, text, reply_markup=open_app(lang))
    except Exception: pass
    if u and u["ref_by"] and given:
        await db.add_credits(u["ref_by"], REF_BONUS)
        try: await bot.send_message(u["ref_by"], bt(await L(u["ref_by"]), "bonus", n=REF_BONUS))
        except Exception: pass

@dp.callback_query(F.data == "dep_done")
async def dep_done(c: CallbackQuery):
    await c.answer(); lang = await L(c.from_user.id)
    if POSTBACK_REQUIRED: return await bot.send_message(c.from_user.id, bt(lang, "wait"))
    try: await c.message.edit_reply_markup(reply_markup=None)
    except Exception: pass
    await grant_access(c.from_user.id)

@dp.message(Command("app"))
async def app_cmd(m: Message):
    lang = await L(m.from_user.id)
    if await db.has_access(m.from_user.id) or m.from_user.id in ADMINS:
        await m.answer(bt(lang, "openq"), reply_markup=open_app(lang))
    else:
        await m.answer(bt(lang, "need"))

@dp.message(Command("invite"))
async def invite(m: Message):
    lang = await L(m.from_user.id); me = await bot.get_me(); n, d = await db.refs(m.from_user.id)
    await m.answer(bt(lang, "invite", link=f"https://t.me/{me.username}?start=ref_{m.from_user.id}", n=n, d=d, ref=REF_BONUS))

# ───────────── АДМИНКА ─────────────
class BC(StatesGroup):
    text = State()
    confirm = State()
adm_kb = kb([btn("📣 Рассылка всем", callback_data="adm_bc_all"), btn("💳 Только с депозитом", callback_data="adm_bc_dep")],
            [btn("👑 Pro-пользователи", callback_data="adm_pros"), btn("🔎 Найти пользователя", callback_data="adm_find")],
            [btn("💰 Платежи", callback_data="adm_pay"), btn("🔄 Обновить", callback_data="adm_stats")])

async def stats_text():
    u, s = await db.admin_stats(); mny = await db.money()
    conv = round(u["dep"] / u["total"] * 100) if u["total"] else 0
    wl = s["w"] + s["l"]; wr = round(s["w"] / wl * 100) if wl else 0
    return (f"📊 <b>QUICK AI · статистика</b>\n\nПользователи: {u['total']} (+{u['new_today']} сегодня)\n"
            f"Подписались: {u['sub']}\nНажали «Далее» после регистрации: {u['reg']}\n"
            f"Депозит: {u['dep']} ({conv}%)\n\nСигналов всего: {s['total']} (сегодня {s['today']})\n"
            f"Плюс / минус: {s['w']} / {s['l']} ({wr}% плюсовых)\n\n"
            f"👑 Pro активно: {mny['pro']}\nCryptoBot: {mny['crypto_n']} оплат ({mny['usdt']:g} USDT) · Stars: {mny['stars_n']} оплат")

@dp.message(Command("admin"))
async def admin(m: Message):
    if m.from_user.id not in ADMINS: return
    await m.answer(await stats_text(), parse_mode="HTML", reply_markup=adm_kb)

@dp.callback_query(F.data == "adm_stats")
async def adm_stats(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer()
    try: await c.message.edit_text(await stats_text(), parse_mode="HTML", reply_markup=adm_kb)
    except Exception: pass
    await c.answer("Обновлено")

@dp.callback_query(F.data.in_({"adm_bc_all", "adm_bc_dep"}))
async def adm_bc(c: CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMINS: return await c.answer()
    await state.set_state(BC.text); await state.update_data(dep=c.data == "adm_bc_dep")
    await c.message.answer("Пришлите текст рассылки одним сообщением (поддерживается HTML-разметка). /cancel — отмена.")
    await c.answer()

@dp.message(Command("cancel"))
async def cancel(m: Message, state: FSMContext):
    await state.clear(); await m.answer("Отменено.")

@dp.message(BC.text)
async def bc_text(m: Message, state: FSMContext):
    if m.from_user.id not in ADMINS or not m.text: return
    await state.update_data(text=m.text); await state.set_state(BC.confirm)
    d = await state.get_data(); ids = await db.all_user_ids(d["dep"])
    await m.answer(f"Предпросмотр:\n\n{m.text}\n\nПолучателей: {len(ids)}", parse_mode="HTML",
                   reply_markup=kb([btn("✅ Отправить", callback_data="adm_send"), btn("✖ Отмена", callback_data="adm_cancel")]))

@dp.callback_query(F.data == "adm_cancel")
async def adm_cancel(c: CallbackQuery, state: FSMContext):
    await state.clear(); await c.message.edit_text("Рассылка отменена."); await c.answer()

@dp.callback_query(F.data == "adm_send")
async def adm_send(c: CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMINS: return await c.answer()
    d = await state.get_data(); await state.clear()
    if not d.get("text"): return await c.answer("Нет текста")
    await c.message.edit_text("Отправляю…"); await c.answer()
    ok = fail = 0
    for uid in await db.all_user_ids(d.get("dep")):
        try: await bot.send_message(uid, d["text"], parse_mode="HTML"); ok += 1
        except Exception: fail += 1
        await asyncio.sleep(0.05)
    await bot.send_message(c.from_user.id, f"Готово. Доставлено: {ok}, не доставлено: {fail}")

# ───────────── PRO: ОПЛАТА ─────────────
def dstr(ts): return datetime.fromtimestamp(ts, timezone.utc).strftime("%d.%m.%Y")
def pro_kb(lang):
    rows = [[btn(bt(lang, "btn_stars"), callback_data="pay_stars")]]
    if CB_TOKEN: rows.append([btn(bt(lang, "btn_crypto"), callback_data="pay_crypto")])
    return kb(*rows)

async def send_pro(uid, lang):
    await bot.send_message(uid, bt(lang, "pro_title", days=PRO_DAYS, stars=PRO_STARS, usdt=f"{PRO_USDT:g}", free=FREE_SIGNALS, ref=REF_BONUS),
                           parse_mode="HTML", reply_markup=pro_kb(lang))

async def stars_info(uid, lang):
    rows = []
    url = f"https://t.me/{OWNER}" if OWNER else (f"tg://user?id={min(ADMINS)}" if ADMINS else None)
    if url: rows.append([btn(bt(lang, "btn_dm"), url=url)])
    rows.append([btn(bt(lang, "btn_sent"), callback_data="stars_sent")])
    await bot.send_message(uid, bt(lang, "stars_text", stars=PRO_STARS, uid=uid, days=PRO_DAYS), parse_mode="HTML", reply_markup=kb(*rows))

async def cb(method, **params):
    async with ClientSession() as ses, ses.post(f"{CB_API}/{method}", json=params, headers={"Crypto-Pay-API-Token": CB_TOKEN}) as r:
        j = await r.json()
    if not j.get("ok"): raise RuntimeError(str(j.get("error")))
    return j["result"]

async def crypto_invoice(uid, lang):
    if not CB_TOKEN: return await bot.send_message(uid, bt(lang, "crypto_off"))
    try:
        inv = await cb("createInvoice", asset="USDT", amount=f"{PRO_USDT:g}", description=f"QUICK AI Pro {PRO_DAYS}d",
                       payload=str(uid), expires_in=3600)
    except Exception:
        logging.exception("createInvoice"); return await bot.send_message(uid, bt(lang, "crypto_off"))
    await db.add_payment(uid, "crypto", PRO_USDT, str(inv["invoice_id"]), "pending")
    url = inv.get("bot_invoice_url") or inv.get("pay_url")
    await bot.send_message(uid, bt(lang, "crypto_text", usdt=f"{PRO_USDT:g}"), parse_mode="HTML",
                           reply_markup=kb([btn(bt(lang, "btn_pay", usdt=f"{PRO_USDT:g}"), url=url)]))

async def pay_dispatch(uid, lang, pay):
    if pay == "pay_stars": await stars_info(uid, lang)
    elif pay == "pay_crypto": await crypto_invoice(uid, lang)
    else: await send_pro(uid, lang)

async def activate_pro(uid, days=None):
    until = await db.set_pro(uid, days or PRO_DAYS); lang = await L(uid)
    try: await bot.send_message(uid, bt(lang, "pro_on", date=dstr(until)), reply_markup=open_app(lang))
    except Exception: pass
    return until

@dp.message(Command("pro"))
async def pro_cmd(m: Message): await send_pro(m.from_user.id, await L(m.from_user.id))

@dp.callback_query(F.data.in_({"pro_menu", "pay_stars", "pay_crypto"}))
async def pro_cb(c: CallbackQuery):
    await c.answer(); await pay_dispatch(c.from_user.id, await L(c.from_user.id), "pro" if c.data == "pro_menu" else c.data)

_last_req: dict = {}
@dp.callback_query(F.data == "stars_sent")
async def stars_sent(c: CallbackQuery):
    uid = c.from_user.id; lang = await L(uid)
    if time.time() - _last_req.get(uid, 0) < 300: return await c.answer(bt(lang, "stars_wait"), show_alert=True)
    _last_req[uid] = time.time(); await c.answer()
    name = f"@{c.from_user.username}" if c.from_user.username else c.from_user.first_name
    for a in ADMINS:
        try:
            await bot.send_message(a, f"💫 Заявка на Pro (Stars {PRO_STARS} ⭐)\n{name} · ID <code>{uid}</code>\nПроверьте подарки и подтвердите.",
                                   parse_mode="HTML", reply_markup=kb([btn("✅ Выдать Pro", callback_data=f"sg:{uid}"), btn("✖ Отклонить", callback_data=f"an:{uid}")]))
        except Exception: pass
    await bot.send_message(uid, bt(lang, "stars_wait"))

# ───────────── АДМИН: ПОЛЬЗОВАТЕЛИ, PRO, ПЛАТЕЖИ ─────────────
class Find(StatesGroup):
    q = State()

def card_kb(uid):
    return kb([btn(f"👑 +{PRO_DAYS} дн", callback_data=f"ag:{uid}:{PRO_DAYS}"), btn("🚫 Снять Pro", callback_data=f"ar:{uid}")],
              [btn("+5 сигналов", callback_data=f"ac:{uid}:5"), btn("+10 сигналов", callback_data=f"ac:{uid}:10")])

async def user_card(u):
    n, d = await db.refs(u["id"]); st = await db.user_stats(u["id"])
    pro = f"👑 Pro до {dstr(u['pro_until'])}" if (u.get("pro_until") or 0) > time.time() else "Free"
    name = f"@{u['username']}" if u.get("username") else (u.get("first_name") or "—")
    return (f"👤 <b>{name}</b> · ID <code>{u['id']}</code>\nЯзык: {u.get('lang') or '—'}\nТариф: {pro}\n"
            f"Сигналов осталось: {u.get('credits') or 0}\nДепозит: {'да' if u['deposited'] else 'нет'}\n"
            f"Друзей: {n} (с доступом {d})\nСделок: {st['total']} (+{st['wins']} / −{st['losses']})")

@dp.callback_query(F.data.regexp(r"^(ag|ar|ac|sg|an):"))
async def adm_actions(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer()
    p = c.data.split(":"); act = p[0]; uid = int(p[1])
    if not await db.get_user(uid): return await c.answer("Пользователь не найден", show_alert=True)
    if act in ("ag", "sg"):
        until = await activate_pro(uid, int(p[2]) if len(p) > 2 else PRO_DAYS)
        if act == "sg": await db.add_payment(uid, "stars", PRO_STARS, None, "paid")
        note = f"✅ Pro выдан до {dstr(until)}"
    elif act == "ar": await db.revoke_pro(uid); note = "🚫 Pro снят"
    elif act == "ac": await db.add_credits(uid, int(p[2])); note = f"➕ Добавлено сигналов: {p[2]}"
    else:
        try: await bot.send_message(uid, bt(await L(uid), "stars_no"))
        except Exception: pass
        note = "✖ Заявка отклонена"
    await c.answer(note)
    try: await c.message.edit_text(note + "\n\n" + await user_card(await db.get_user(uid)), parse_mode="HTML", reply_markup=card_kb(uid))
    except Exception: pass

def _need_admin(m): return m.from_user.id in ADMINS

@dp.message(Command("grant"))
async def cmd_grant(m: Message, command: CommandObject):
    if not _need_admin(m): return
    a = (command.args or "").split()
    if not a: return await m.answer("/grant ID|@username [дней] — выдать Pro")
    u = await db.get_user_by(a[0])
    if not u: return await m.answer("Пользователь не найден (он должен хотя бы раз запустить бота).")
    until = await activate_pro(u["id"], int(a[1]) if len(a) > 1 and a[1].isdigit() else PRO_DAYS)
    await m.answer(f"✅ Pro до {dstr(until)}\n\n" + await user_card(await db.get_user(u["id"])), parse_mode="HTML", reply_markup=card_kb(u["id"]))

@dp.message(Command("revoke"))
async def cmd_revoke(m: Message, command: CommandObject):
    if not _need_admin(m): return
    u = await db.get_user_by((command.args or "").strip() or "0")
    if not u: return await m.answer("/revoke ID|@username — снять Pro")
    await db.revoke_pro(u["id"]); await m.answer("🚫 Pro снят\n\n" + await user_card(await db.get_user(u["id"])), parse_mode="HTML", reply_markup=card_kb(u["id"]))

@dp.message(Command("credits"))
async def cmd_credits(m: Message, command: CommandObject):
    if not _need_admin(m): return
    a = (command.args or "").split(); u = await db.get_user_by(a[0]) if a else None
    if not u or len(a) < 2 or not a[1].lstrip("-").isdigit(): return await m.answer("/credits ID|@username N — добавить сигналы")
    await db.add_credits(u["id"], int(a[1])); await m.answer("➕ Готово\n\n" + await user_card(await db.get_user(u["id"])), parse_mode="HTML", reply_markup=card_kb(u["id"]))

@dp.message(Command("user"))
async def cmd_user(m: Message, command: CommandObject):
    if not _need_admin(m): return
    u = await db.get_user_by((command.args or "").strip() or "0")
    if not u: return await m.answer("/user ID|@username — карточка пользователя")
    await m.answer(await user_card(u), parse_mode="HTML", reply_markup=card_kb(u["id"]))

async def pros_text():
    rows = await db.pros()
    lines = [f"• {'@' + r['username'] if r['username'] else (r['first_name'] or '—')} · <code>{r['id']}</code> · до {dstr(r['pro_until'])}" for r in rows[:40]]
    return f"👑 <b>Pro-пользователи ({len(rows)})</b>\n\n" + ("\n".join(lines) if lines else "Пока нет")

@dp.message(Command("pros"))
async def cmd_pros(m: Message):
    if _need_admin(m): await m.answer(await pros_text(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_pros")
async def adm_pros(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer()
    await c.answer(); await c.message.answer(await pros_text(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_pay")
async def adm_pay(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer()
    await c.answer(); rows = await db.payments_last(10)
    st = {"paid": "✅", "pending": "⏳", "expired": "⌛"}
    lines = [f"{st.get(r['status'], '•')} {r['kind']} · {r['amount']:g} · {'@' + r['username'] if r['username'] else r['user_id']} · {dstr(r['created'])}" for r in rows]
    await c.message.answer("💰 <b>Последние платежи</b>\n\n" + ("\n".join(lines) if lines else "Пока нет"), parse_mode="HTML")

@dp.callback_query(F.data == "adm_find")
async def adm_find(c: CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMINS: return await c.answer()
    await state.set_state(Find.q); await c.answer()
    await c.message.answer("Пришлите ID или @username пользователя. /cancel — отмена.")

@dp.message(Find.q)
async def find_q(m: Message, state: FSMContext):
    if not _need_admin(m) or not m.text: return
    await state.clear(); u = await db.get_user_by(m.text)
    if not u: return await m.answer("Не найден.")
    await m.answer(await user_card(u), parse_mode="HTML", reply_markup=card_kb(u["id"]))

# ───────────── ФОНОВЫЕ ЗАДАЧИ ─────────────
async def crypto_watcher():
    """Проверяет счета CryptoBot и включает Pro сразу после оплаты."""
    while True:
        await asyncio.sleep(20)
        try:
            pend = await db.pending_crypto(int(time.time()) - 7200)
            if not pend: continue
            res = await cb("getInvoices", invoice_ids=",".join(p["invoice_id"] for p in pend))
            for it in (res.get("items", []) if isinstance(res, dict) else res):
                iid = str(it.get("invoice_id")); st = it.get("status")
                if st == "paid":
                    if await db.mark_paid(iid):
                        uid = next(p["user_id"] for p in pend if p["invoice_id"] == iid); await activate_pro(uid)
                elif st == "expired": await db.mark_expired(iid)
        except Exception:
            logging.exception("crypto_watcher")

async def pro_watcher():
    """Напоминает о скором окончании Pro и сообщает об окончании."""
    while True:
        try:
            now = int(time.time())
            for u in await db.expiring(now, now + 3 * 86400):
                lang = u.get("lang") or "ru"
                try: await bot.send_message(u["id"], bt(lang, "pro_soon", date=dstr(u["pro_until"])), reply_markup=pro_kb(lang))
                except Exception: pass
                await db.mark_notified(u["id"], u["pro_until"])
            for u in await db.expired_unsent(now):
                lang = u.get("lang") or "ru"
                try: await bot.send_message(u["id"], bt(lang, "pro_end"), reply_markup=pro_kb(lang))
                except Exception: pass
                await db.mark_exp_sent(u["id"], u["pro_until"])
        except Exception:
            logging.exception("pro_watcher")
        await asyncio.sleep(3600)

def calc_result(s, cs):
    ex = cs[-1]["c"]; diff = ex - s["entry"]
    res = "D" if abs(diff) <= abs(s["entry"]) * 1e-7 else ("W" if (s["dir"] == "CALL") == (diff > 0) else "L")
    return res, ex

async def notify_result(s, res, ex):
    lang = await L(s["user_id"]); n = max(1, (s["expires"] - s["created"]) // 60)
    txt = (f"{bt(lang, res)}\n{s['pair']} {'▲' if s['dir'] == 'CALL' else '▼'} {s['dir']} · {n} {bt(lang, 'min')}\n"
           f"{fmt(s['pair'], s['entry'])} → {fmt(s['pair'], ex)}")
    try: await bot.send_message(s["user_id"], txt)
    except Exception: pass

async def settler():
    """Закрывает сделки по истечении экспирации и шлёт результат в бот, даже если приложение закрыто."""
    while True:
        try:
            now = int(time.time())
            for s in await db.due_signals(now):
                if now - s["expires"] > 900:
                    await db.settle_signal(s["id"], None, "X"); continue
                try: cs = await engine.candles(s["pair"], s["tf"], fresh=True)
                except engine.DataError: continue
                res, ex = calc_result(s, cs)
                if await db.settle_signal(s["id"], ex, res): await notify_result(s, res, ex)
        except Exception:
            logging.exception("settler")
        await asyncio.sleep(5)

async def daily_report():
    while True:
        await asyncio.sleep(60)
        try:
            now = datetime.now(timezone.utc)
            if now.hour == REPORT_HOUR and await db.meta_get("report") != str(now.date()):
                await db.meta_set("report", str(now.date())); txt = await stats_text()
                for a in ADMINS:
                    try: await bot.send_message(a, "🗓 Ежедневный отчёт\n\n" + txt, parse_mode="HTML")
                    except Exception: pass
        except Exception:
            logging.exception("report")

async def td_ws():
    """Поток цен Twelve Data (только платный тариф). Включается переменной TD_WS=1."""
    while True:
        try:
            async with ClientSession() as ses, ses.ws_connect(f"wss://ws.twelvedata.com/v1/quotes/price?apikey={TD_KEY}") as ws:
                await ws.send_json({"action": "subscribe", "params": {"symbols": ",".join(PAIRS)}})
                async def hb():
                    while True: await asyncio.sleep(10); await ws.send_json({"action": "heartbeat"})
                t = asyncio.create_task(hb())
                try:
                    async for msg in ws:
                        if msg.type == WSMsgType.TEXT:
                            d = json.loads(msg.data)
                            if d.get("event") == "price": LIVE[d["symbol"]] = (float(d["price"]), time.time())
                finally: t.cancel()
        except Exception as e:
            logging.warning("td_ws: %s", e)
        await asyncio.sleep(5)

async def otc_stream():
    """Живые цены Pocket Option OTC из OTCharts (нужен платный тариф со стримом)."""
    global OTC_LIVE
    syms = {engine.otc_symbol(p): p for p in engine.OTC_PAIRS}
    while True:
        wait = 10
        try:
            async with ClientSession(timeout=ClientTimeout(total=None, sock_read=60)) as ses, ses.get(
                    "https://otcharts.com/v1/stream", params=dict(venue=engine.OTC_VENUE, symbol=",".join(syms)),
                    headers={"Authorization": f"Bearer {engine.OTC_KEY}", "User-Agent": "quick-ai-bot/1.0"}) as r:
                if r.status != 200:
                    logging.warning("otc_stream: HTTP %s (бесплатный ключ не даёт стрим)", r.status)
                    wait = 300 if r.status in (401, 402, 403) else 30
                else:
                    ev = None
                    async for raw in r.content:
                        line = raw.decode("utf-8", "ignore").strip()
                        if line.startswith("event:"): ev = line[6:].strip()
                        elif line.startswith("data:") and ev:
                            d = json.loads(line[5:])
                            if ev == "connected": OTC_LIVE = True
                            elif ev == "tick" and d.get("symbol") in syms: LIVE[syms[d["symbol"]]] = (float(d["price"]), time.time())
                            elif ev == "replaced": wait = 70
        except Exception as e:
            logging.warning("otc_stream: %s", e)
        OTC_LIVE = False
        await asyncio.sleep(wait)

@dp.message(Command("otcsymbols"))
async def cmd_otcsymbols(m: Message):
    """Админ: каталог OTC-инструментов вашего ключа с выплатами (1 запрос к OTCharts)."""
    if m.from_user.id not in ADMINS: return
    if not engine.OTC_KEY: return await m.answer("Ключ OTCHARTS_API_KEY / OTCHARTS_KEY не задан.")
    try:
        async with ClientSession(timeout=ClientTimeout(total=15)) as ses, ses.get("https://otcharts.com/v1/symbols", params=dict(venue=engine.OTC_VENUE),
                headers={"Authorization": f"Bearer {engine.OTC_KEY}", "User-Agent": "quick-ai-bot/1.0"}) as r:
            st = r.status; d = await r.json(content_type=None)
    except Exception as e:
        return await m.answer(f"Ошибка запроса: {e}")
    if st != 200: return await m.answer(f"OTCharts: {st} {d.get('error') if isinstance(d, dict) else ''}")
    rows = [f"{x['symbol']} · {x.get('payout') if x.get('payout') is not None else '—'}% · {'открыт' if x.get('open') else 'закрыт' if x.get('open') is False else '?'}" for x in d.get("symbols", [])[:60]]
    await m.answer(f"Инструментов: {d.get('count')}\nПоказаны первые 60. Имя в OTC_PAIRS: «EUR/USD OTC» для EURUSD_otc.\n\n" + "\n".join(rows))

# ───────────── API ДЛЯ WEBAPP ─────────────
def err(msg, status, code, **extra): return web.json_response({"error": msg, "code": code, **extra}, status=status)

def check_init(init_data):
    try:
        p = dict(parse_qsl(init_data, keep_blank_values=True)); h = p.pop("hash")
        dcs = "\n".join(f"{k}={v}" for k, v in sorted(p.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest(), h): return None
        if time.time() - int(p.get("auth_date", 0)) > 86400: return None
        return json.loads(p["user"])["id"]
    except Exception:
        return None

async def auth(req):
    if DEV_MODE: return 0
    uid = check_init(req.headers.get("X-Init-Data", ""))
    if uid is None: raise web.HTTPUnauthorized(text=json.dumps({"error": "unauth", "code": "unauth"}), content_type="application/json")
    if uid not in ADMINS and not await db.has_access(uid):
        raise web.HTTPForbidden(text=json.dumps({"error": "forbid", "code": "forbid"}), content_type="application/json")
    return uid

def valid(pair, tf): return pair in ALL_PAIRS and tf in TFSEC

async def api_chart(req):
    await auth(req)
    pair, tf = req.query.get("pair", ""), req.query.get("tf", "")
    if not valid(pair, tf): return err("bad", 400, "bad")
    try: cs = await engine.candles(pair, tf)
    except engine.DataError as e: return err(str(e), 502, "data")
    return web.json_response({"candles": cs[-80:], "live": OTC_LIVE if pair in engine.OTC_PAIRS else TD_WS})

async def api_price(req):
    await auth(req)
    v = LIVE.get(req.query.get("pair", ""))
    if v and time.time() - v[1] < 10: return web.json_response({"price": v[0]})
    return web.json_response({"price": None})

async def api_lang(req):
    uid = await auth(req)
    try: lang = (await req.json()).get("lang")
    except Exception: lang = None
    if lang in B and uid: await db.set_lang(uid, lang)
    return web.json_response({"ok": True})

async def plan_info(uid):
    if uid == 0 or uid in ADMINS: return dict(pro=True, until=0, credits=0)
    u = await db.get_user(uid) or {}; pu = u.get("pro_until") or 0
    return dict(pro=pu > time.time(), until=pu * 1000, credits=u.get("credits") or 0)

BOT_USERNAME = ""
async def api_me(req):
    global BOT_USERNAME
    uid = await auth(req)
    if not BOT_USERNAME: BOT_USERNAME = (await bot.get_me()).username
    act = await db.active_signal(uid); a = None
    if act and time.time() < act["expires"] + 300:
        a = dict(id=act["id"], pair=act["pair"], tf=act["tf"], dir=act["dir"], entry=act["entry"],
                 end=act["expires"] * 1000, dur=act["expires"] - act["created"])
    n, d = await db.refs(uid)
    return web.json_response(dict(pairs=ALL_PAIRS, uid=uid, bot=BOT_USERNAME, plan=await plan_info(uid), active=a,
        stats=await db.user_stats(uid), history=await db.history(uid), streak=await db.loss_streak(uid),
        lang=(await db.get_lang(uid)) if uid else "ru", refs=dict(n=n, d=d), profile=await db.profile_stats(uid),
        offer=dict(stars=PRO_STARS, usdt=PRO_USDT, days=PRO_DAYS, ref=REF_BONUS, free=FREE_SIGNALS), crypto=bool(CB_TOKEN)))

def tf_for(exp): return "1min" if exp <= 180 else "5min" if exp <= 600 else "15min" if exp <= 1800 else "30min" if exp <= 3600 else "1h"

async def api_analyze(req):
    uid = await auth(req)
    try: b = await req.json()
    except Exception: return err("bad", 400, "bad")
    pair, lang = b.get("pair", ""), b.get("lang", "ru")
    try: exp = int(b.get("exp") or TFSEC.get(b.get("tf"), 0))
    except (TypeError, ValueError): exp = 0
    if pair not in ALL_PAIRS or not 60 <= exp <= 14400: return err("bad", 400, "bad")
    atf = tf_for(exp)
    act = await db.active_signal(uid)
    if act:
        if time.time() < act["expires"] + 90: return err("busy", 409, "busy")
        await db.settle_signal(act["id"], None, "X")
    pl = await plan_info(uid)
    if pl["pro"]:
        if await db.signals_today(uid) >= PRO_DAILY_CAP: return err("limit", 429, "limit", n=PRO_DAILY_CAP)
    elif pl["credits"] <= 0: return err("nocredits", 402, "nocredits", n=REF_BONUS)
    try: a = await engine.analyze(pair, atf, lang)
    except engine.DataError as e: return err(str(e), 502, "data")
    sig = None
    if a["direction"] != "WAIT":
        end = int(time.time()) + exp
        sid = await db.add_signal(uid, pair, atf, a["direction"], a["strength"], a["entry"], end)
        sig = dict(id=sid, entry=a["entry"], end=end * 1000, dur=exp, tf=atf)
        if not pl["pro"] and await db.consume_credit(uid): pl["credits"] -= 1
    return web.json_response(dict(analysis=a, signal=sig, plan=pl))

async def api_settle(req):
    uid = await auth(req)
    try: sid = int((await req.json()).get("id"))
    except Exception: return err("bad", 400, "bad")
    s = await db.get_signal(sid)
    if not s or s["user_id"] != uid: return err("notfound", 404, "notfound")
    if s["result"]: return web.json_response(dict(res=s["result"], entry=s["entry"], exit=s["exit_price"], pair=s["pair"]))
    if time.time() < s["expires"]: return err("early", 425, "early")
    try: cs = await engine.candles(s["pair"], s["tf"], fresh=True)
    except engine.DataError as e: return err(str(e), 502, "data")
    res, ex = calc_result(s, cs)
    if await db.settle_signal(sid, ex, res):
        if uid: await notify_result(s, res, ex)
        return web.json_response(dict(res=res, entry=s["entry"], exit=ex, pair=s["pair"]))
    s = await db.get_signal(sid)
    return web.json_response(dict(res=s["result"], entry=s["entry"], exit=s["exit_price"], pair=s["pair"]))

async def postback(req):
    q = dict(req.query)
    if req.method == "POST":
        try: q.update(dict(await req.post()))
        except Exception: pass
    if POSTBACK_SECRET and not hmac.compare_digest(q.get("secret", ""), POSTBACK_SECRET):
        return web.Response(status=403, text="forbidden")
    try: uid = int(q.get("uid", ""))
    except ValueError: return web.Response(status=400, text="uid required")
    ev = (q.get("event") or "").lower()
    try: amount = float(q.get("sum") or 0)
    except ValueError: amount = 0.0
    if not await db.get_user(uid): return web.Response(text="unknown user")
    if ev in ("reg", "registration"): await db.set_flag(uid, registered=1)
    elif ev in ("dep", "deposit", "ftd", "first_deposit"):
        if amount and amount < 10: return web.Response(text="below minimum")
        await grant_access(uid, amount)
    return web.Response(text="ok")

async def index(_):
    return web.FileResponse(BASE / "webapp" / "index.html", headers={"Cache-Control": "no-cache"})

async def main():
    logging.basicConfig(level=logging.INFO)
    await db.init()
    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/health", lambda r: web.Response(text="ok")),
                    web.get("/api/chart", api_chart), web.get("/api/me", api_me), web.get("/api/price", api_price),
                    web.post("/api/analyze", api_analyze), web.post("/api/settle", api_settle), web.post("/api/lang", api_lang),
                    web.route("*", "/postback", postback)])
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_my_commands([BotCommand(command="start", description="Start"), BotCommand(command="app", description="Terminal"),
                               BotCommand(command="invite", description="Invite friends"), BotCommand(command="pro", description="Pro"), BotCommand(command="lang", description="Language")])
    tasks = [asyncio.create_task(settler()), asyncio.create_task(daily_report()), asyncio.create_task(pro_watcher())]
    if CB_TOKEN: tasks.append(asyncio.create_task(crypto_watcher()))
    if TD_WS: tasks.append(asyncio.create_task(td_ws()))
    if engine.OTC_PAIRS: tasks.append(asyncio.create_task(otc_stream()))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
