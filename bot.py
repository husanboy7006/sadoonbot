import logging
import asyncio
import os
import uuid
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from google import genai as google_genai
from openai import AsyncOpenAI
from database import Database
import mixer
from smm_prompts import post as smm_post, reels as smm_reels, plan as smm_plan
from smm_prompts import hashtag as smm_hashtag, caption as smm_caption, strategy as smm_strategy

# --- LOGGING ---
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIG ---
TOKEN = os.getenv("HF_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("API_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY") or os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")
if not ADMIN_ID:
    print("❌ ADMIN_ID environment variable not set!")
    exit(1)
ADMIN_ID = int(ADMIN_ID)

if not TOKEN:
    print("❌ ERROR: Telegram BOT_TOKEN topilmadi!")
    exit(1)

gemini_client = None
if GEMINI_KEY:
    gemini_client = google_genai.Client(api_key=GEMINI_KEY)

openai_client = None
if OPENAI_API_KEY:
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

db = Database()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- STATES ---
class MixState(StatesGroup):
    waiting_translate = State()
    waiting_download = State()
    waiting_clip_photo = State()
    waiting_clip_audio = State()
    waiting_feedback = State()
    # AI Suhbat
    waiting_chat = State()
    # SMM states
    smm_post = State()
    smm_reels = State()
    smm_plan = State()
    smm_hashtag = State()
    smm_caption = State()
    smm_strategy = State()
    # Admin
    waiting_broadcast = State()

# --- KEYBOARDS ---
from calc_parser import safe_calc, format_result, CalcError
import aiohttp as _aiohttp

user_calc_expr: dict = {}
user_calc_history: dict = {}
user_calc_awaiting: dict = {}

def _b(t, d): return InlineKeyboardButton(text=t, callback_data=d)

def make_calc_kb(mode="basic"):
    if mode == "science":
        rows = [
            [_b("sin", "c_sin("), _b("cos", "c_cos("), _b("tan", "c_tan("), _b("⌫", "c_back")],
            [_b("log", "c_log("), _b("ln", "c_ln("), _b("√", "c_sqrt("), _b("x²", "c_^2")],
            [_b("π", "c_π"), _b("e", "c_e"), _b("(", "c_("), _b(")", "c_)")],
            [_b("xⁿ", "c_^"), _b("1/x", "c_1/x"), _b("n!", "c_!"), _b("C", "c_C")],
            [_b("7", "c_7"), _b("8", "c_8"), _b("9", "c_9"), _b("÷", "c_÷")],
            [_b("4", "c_4"), _b("5", "c_5"), _b("6", "c_6"), _b("×", "c_×")],
            [_b("1", "c_1"), _b("2", "c_2"), _b("3", "c_3"), _b("−", "c_−")],
            [_b("🔢", "c_mode_basic"), _b("0", "c_0"), _b(".", "c_."), _b("=", "c_=")],
        ]
    else:
        rows = [
            [_b("C", "c_C"), _b("⌫", "c_back"), _b("%", "c_%"), _b("÷", "c_÷")],
            [_b("7", "c_7"), _b("8", "c_8"), _b("9", "c_9"), _b("×", "c_×")],
            [_b("4", "c_4"), _b("5", "c_5"), _b("6", "c_6"), _b("−", "c_−")],
            [_b("1", "c_1"), _b("2", "c_2"), _b("3", "c_3"), _b("+", "c_+")],
            [_b("🔬 Ilmiy", "c_mode_science"), _b("0", "c_0"), _b(".", "c_."), _b("=", "c_=")],
            [_b("(", "c_("), _b(")", "c_)"), _b("📜", "c_history"), _b("🏠", "c_menu")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def make_result_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b("🔢 Yana hisoblash", "c_mode_basic"), _b("📜 Tarix", "c_history")],
        [_b("💱 Valyuta", "c_open_currency"), _b("📏 Birliklar", "c_open_convert")],
        [_b("🏠 Bosh menyu", "c_menu")],
    ])

def make_history_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b("🗑 Tarixni tozalash", "c_clear_history"), _b("🔢 Kalkulator", "c_mode_basic")],
        [_b("🏠 Bosh menyu", "c_menu")],
    ])

def make_currency_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b("🇺🇸 USD → UZS", "c_cur_USD_UZS"), _b("🇺🇿 UZS → USD", "c_cur_UZS_USD")],
        [_b("🇪🇺 EUR → UZS", "c_cur_EUR_UZS"), _b("🇷🇺 RUB → UZS", "c_cur_RUB_UZS")],
        [_b("🔢 Kalkulator", "c_mode_basic"), _b("🏠 Yopish", "c_close")],
    ])

def make_convert_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b("km ↔ mi", "c_conv_km_mi"), _b("kg ↔ lb", "c_conv_kg_lb")],
        [_b("°C ↔ °F", "c_conv_c_f"), _b("m ↔ ft", "c_conv_m_ft")],
        [_b("🔢 Kalkulator", "c_mode_basic"), _b("🏠 Yopish", "c_close")],
    ])

async def get_currency_rates():
    try:
        async with _aiohttp.ClientSession() as s:
            async with s.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/", timeout=_aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
                return {item["Ccy"]: float(item["Rate"]) for item in data}
    except:
        return {}

async def convert_currency(amount, from_cur, to_cur):
    rates = await get_currency_rates()
    if not rates: raise Exception("CBU serveriga ulanib bo'lmadi")
    if from_cur == "UZS":
        if to_cur not in rates: raise Exception(f"{to_cur} topilmadi")
        return amount / rates[to_cur]
    elif to_cur == "UZS":
        if from_cur not in rates: raise Exception(f"{from_cur} topilmadi")
        return amount * rates[from_cur]
    else:
        if from_cur not in rates or to_cur not in rates: raise Exception("Kurs topilmadi")
        return amount * rates[from_cur] / rates[to_cur]

def convert_unit(amount, conv_type):
    c = {
        "km_mi": (lambda x: x * 0.621371, lambda x: x / 0.621371, "km", "mi"),
        "kg_lb": (lambda x: x * 2.20462, lambda x: x / 2.20462, "kg", "lb"),
        "c_f":   (lambda x: x * 9/5 + 32, lambda x: (x-32) * 5/9, "°C", "°F"),
        "m_ft":  (lambda x: x * 3.28084, lambda x: x / 3.28084, "m", "ft"),
    }
    if conv_type not in c: raise ValueError("Noma'lum tur")
    fwd, bwd, u1, u2 = c[conv_type]
    return (f"📏 <b>Birlik o'zgartirish</b>\n\n"
            f"<code>{amount:,.2f} {u1}</code> = <b>{fwd(amount):,.4f} {u2}</b>\n"
            f"<code>{amount:,.2f} {u2}</code> = <b>{bwd(amount):,.4f} {u1}</b>")

SMM_FREE_DAILY = int(os.getenv("FREE_DAILY_LIMIT", "3"))
SMM_PREMIUM_DAILY = int(os.getenv("PREMIUM_DAILY_LIMIT", "30"))
SMM_MAX_TOKENS = int(os.getenv("MAX_TOKENS", "5000"))
SMM_TEMPERATURE = float(os.getenv("TEMPERATURE", "0.8"))
PAYMENT_ADMIN = os.getenv("PAYMENT_ADMIN", "@husanjon007")

main_keyboard = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="🆓 Bepul xizmatlar")],
        [types.KeyboardButton(text="💎 Pullik xizmatlar")],
        [types.KeyboardButton(text="✍️ Takliflar")]
    ],
    resize_keyboard=True
)

free_keyboard = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="📥 Yuklab olish"), types.KeyboardButton(text="🌐 Tilmoch AI")],
        [types.KeyboardButton(text="🤖 AI Suhbat"), types.KeyboardButton(text="🧮 Kalkulator")],
        [types.KeyboardButton(text="🎬 Klip Yaratish")],
        [types.KeyboardButton(text="🔍 Shazam")],
        [types.KeyboardButton(text="🔙 Orqaga")]
    ],
    resize_keyboard=True
)

chat_keyboard = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="🗑 Suhbatni tozala")],
        [types.KeyboardButton(text="🔙 Chiqish")]
    ],
    resize_keyboard=True
)

paid_keyboard = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="✍️ SMM Studio")],
        [types.KeyboardButton(text="💎 Plus olish"), types.KeyboardButton(text="📊 Mening limitim")],
        [types.KeyboardButton(text="🔙 Orqaga")]
    ],
    resize_keyboard=True
)

smm_keyboard = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="📝 Post yozish"), types.KeyboardButton(text="🎬 Reels ssenariy")],
        [types.KeyboardButton(text="📅 Kontent plan"), types.KeyboardButton(text="#️⃣ Hashtag")],
        [types.KeyboardButton(text="💬 Caption"), types.KeyboardButton(text="📊 Strategiya")],
        [types.KeyboardButton(text="🔙 Orqaga")]
    ],
    resize_keyboard=True
)

# --- HANDLERS ---
@dp.message(Command("start"))
async def start(message: Message):
    print(f"[*] /start received from {message.from_user.id}")
    try:
        db.add_user(message.from_user.id, message.from_user.full_name)
    except Exception as e:
        print(f"[!] DB Error: {e}")
    await message.answer(
        f"Xush kelibsiz, {message.from_user.full_name}! 👋\n\n"
        f"🤖 <b>Sadoon AI</b> — sizning aqlli yordamchingiz!\n\n"
        f"🆓 <b>Bepul xizmatlar:</b>\n"
        f"📥 Video yuklab olish (TikTok, Instagram, YouTube)\n"
        f"🌐 Tilmoch AI (O'zbek ↔ Rus ↔ Xitoy)\n"
        f"🎬 Klip yaratish (rasm + musiqa)\n\n"
        f"💎 <b>Pullik xizmatlar:</b>\n"
        f"✍️ SMM Studio — AI yordamida kontent yaratish\n"
        f"   📝 Post • 🎬 Reels • 📅 Plan\n"
        f"   #️⃣ Hashtag • 💬 Caption • 📊 Strategiya\n\n"
        f"🆓 Kunlik <b>{SMM_FREE_DAILY} ta</b> bepul SMM so'rov\n\n"
        f"📌 Boshlash uchun quyidagi tugmalardan foydalaning 👇",
        parse_mode="HTML", reply_markup=main_keyboard
    )

@dp.message(Command("stats"))
async def user_stats(message: Message):
    uid = message.from_user.id
    used = db.get_daily_smm(uid)
    prem = db.is_premium(uid)
    if prem:
        until = db.get_user_metadata(uid).get("premium_until", "")
        status = f"💎 Plus ({until} gacha)"
        limit_text = f"{used}/{SMM_PREMIUM_DAILY} ta ishlatildi"
    else:
        status = "🆓 Free"
        limit_text = f"{used}/{SMM_FREE_DAILY} ta ishlatildi"
    await message.answer(
        f"📊 <b>Sizning hisobingiz</b>\n\n"
        f"👤 Tarif: {status}\n"
        f"📝 SMM bugun: {limit_text}\n"
        f"🆔 ID: <code>{uid}</code>",
        parse_mode="HTML"
    )

@dp.message(Command("admin"))
async def admin_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("⛔ Ruxsat yo'q.")
    report = db.get_stats_report()
    await message.answer(report, parse_mode="HTML")


@dp.message(Command("reklama"))
async def broadcast_start(message: Message, state: FSMContext):
    """Barcha foydalanuvchilarga reklama yuborish — faqat admin"""
    if message.from_user.id != ADMIN_ID:
        return await message.answer("⛔ Ruxsat yo'q.")
    await message.answer(
        "📢 <b>Reklama yuborish</b>\n\n"
        "Yubormoqchi bo'lgan xabarni yozing.\n"
        "Rasm, video yoki matn bo'lishi mumkin.\n\n"
        "❌ Bekor qilish uchun /bekor yozing.",
        parse_mode="HTML"
    )
    await state.set_state(MixState.waiting_broadcast)


@dp.message(MixState.waiting_broadcast, F.text | F.photo | F.video)
async def broadcast_send(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await state.clear()
        return
    await state.clear()
    users = db.get_all_users()
    total = len(users)
    sent = 0
    failed = 0
    status_msg = await message.answer(f"⏳ Yuborilmoqda... 0/{total}")
    for i, user_id in enumerate(users):
        try:
            if message.photo:
                await bot.send_photo(
                    chat_id=int(user_id),
                    photo=message.photo[-1].file_id,
                    caption=message.caption or "",
                    parse_mode="HTML"
                )
            elif message.video:
                await bot.send_video(
                    chat_id=int(user_id),
                    video=message.video.file_id,
                    caption=message.caption or "",
                    parse_mode="HTML"
                )
            else:
                await bot.send_message(
                    chat_id=int(user_id),
                    text=message.text,
                    parse_mode="HTML"
                )
            sent += 1
        except Exception:
            failed += 1
        if (i + 1) % 10 == 0:
            try:
                await status_msg.edit_text(f"⏳ Yuborilmoqda... {i+1}/{total}")
            except Exception:
                pass
        await asyncio.sleep(0.05)
    await status_msg.edit_text(
        f"✅ <b>Reklama yuborildi!</b>\n\n"
        f"👥 Jami: {total} ta\n"
        f"✅ Yuborildi: {sent} ta\n"
        f"❌ Bloklanган: {failed} ta",
        parse_mode="HTML"
    )

@dp.message(F.text == "📊 Mening limitim")
async def check_limit(message: Message):
    uid = message.from_user.id
    used = db.get_daily_smm(uid)
    prem = db.is_premium(uid)
    if prem:
        until = db.get_user_metadata(uid).get("premium_until", "")
        remaining = max(0, SMM_PREMIUM_DAILY - used)
        await message.answer(
            f"💎 <b>Plus aktiv</b>\n\n📅 {until} gacha\n✅ Kuniga {SMM_PREMIUM_DAILY} ta SMM so'rov\n📊 Qoldi: {remaining} ta",
            parse_mode="HTML", reply_markup=paid_keyboard
        )
    else:
        remaining = max(0, SMM_FREE_DAILY - used)
        await message.answer(
            f"📊 <b>Kunlik limitingiz</b>\n\n"
            f"📝 SMM bugun: {used}/{SMM_FREE_DAILY} ta\n"
            f"🆓 Qoldi: {remaining} ta\n\n"
            f"💎 Ko'proq ishlash uchun Plus oling!",
            parse_mode="HTML", reply_markup=paid_keyboard
        )

@dp.message(F.text == "💎 Plus olish")
async def premium_start(message: Message):
    await message.answer(
        f"💎 <b>Plus Rejim</b>\n\n"
        f"✅ Kuniga {SMM_PREMIUM_DAILY} ta SMM so'rov\n"
        f"🆓 Bepul: kuniga {SMM_FREE_DAILY} ta\n\n"
        f"💰 <b>Narx:</b> 29,000 so'm/oy\n\n"
        f"To'lov uchun adminga yozing: {PAYMENT_ADMIN}\n"
        f"To'lovdan keyin chekni botga yuboring.",
        parse_mode="HTML"
    )

@dp.message(F.text == "🆓 Bepul xizmatlar")
async def free_menu(message: Message):
    await message.answer("🆓 <b>Bepul xizmatlar</b>\n\nBitta tanlang:", reply_markup=free_keyboard, parse_mode="HTML")

@dp.message(F.text == "💎 Pullik xizmatlar")
async def paid_menu(message: Message):
    uid = message.from_user.id
    used = db.get_daily_smm(uid)
    prem = db.is_premium(uid)
    if prem:
        until = db.get_user_metadata(uid).get("premium_until", "")
        remaining = max(0, SMM_PREMIUM_DAILY - used)
        info = f"💎 Plus aktiv ({until} gacha) — {remaining}/{SMM_PREMIUM_DAILY} ta qoldi"
    else:
        remaining = max(0, SMM_FREE_DAILY - used)
        info = f"🆓 Bugun qoldi: {remaining}/{SMM_FREE_DAILY} ta bepul so'rov"
    await message.answer(f"💎 <b>Pullik xizmatlar</b>\n\n{info}\n\nBitta tanlang:", reply_markup=paid_keyboard, parse_mode="HTML")

@dp.message(F.text == "🌐 Tilmoch AI")
async def trans_start(message: Message, state: FSMContext):
    await message.answer("✍️ Tarjima qilinadigan xabarni yuboring.")
    await state.set_state(MixState.waiting_translate)

@dp.message(MixState.waiting_translate, F.text)
async def handle_translate(message: Message, state: FSMContext):
    groq_key = os.getenv("GROQ_KEY")
    if not groq_key:
        await message.answer("❌ AI sozlanmagan.")
        await state.clear()
        return
    wait_msg = await message.answer("⏳ Tarjima qilinmoqda...")
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=groq_key)
        system = (
            "Sen Tilmoch AI — O'zbek, Rus va Xitoy tillari o'rtasida tezkor tarjimon.\n"
            "Qoidalar: kirish gaplari yozma, darhol tarjima qil.\n"
            "Til aniqlash: Latin/o'zbek harflar → Ruscha VA Xitoycha tarjima.\n"
            "Kirill/rus harflar → O'zbekcha tarjima.\n"
            "Xitoy ierogliflari → O'zbekcha tarjima.\n"
            "Format (o'zbek uchun):\n📝 Original: [matn]\n🇷🇺 Ruscha: [tarjima]\n🇨🇳 Xitoycha: [tarjima]\n🔤 Talaffuz: [pinyin]\n"
            "Format (rus uchun):\n📝 Original: [matn]\n🇺🇿 O'zbekcha: [tarjima]"
        )
        res = await asyncio.wait_for(
            client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": message.text}
                ],
                max_tokens=1000,
            ), timeout=30
        )
        reply = res.choices[0].message.content
        try: await wait_msg.delete()
        except: pass
        await message.answer(reply)
        db.log_stats(message.from_user.id, "translate")
    except asyncio.TimeoutError:
        await wait_msg.edit_text("⏰ Vaqt tugadi. Qaytadan urinib ko'ring.")
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xato: {str(e)[:200]}")
    await state.clear()

@dp.message(F.text == "📥 Yuklab olish")
async def download_start(message: Message, state: FSMContext):
    await message.answer("🔗 Havolani yuboring.")
    await state.set_state(MixState.waiting_download)

@dp.message(MixState.waiting_download, F.text)
async def handle_download(message: Message, state: FSMContext):
    url = extract_url(message.text)
    if not url: return await message.answer("❌ Xato havola.")
    wait_msg = await message.answer("⏳ Yuklanmoqda...")
    output = f"temp/v_{uuid.uuid4()}.mp4"
    try:
        success = await asyncio.wait_for(mixer.download_video(url, output), timeout=55)
        if success:
            await message.answer_video(video=FSInputFile(output))
            db.log_stats(message.from_user.id, "download")
        else:
            await message.answer("❌ Yuklab bo'lmadi.")
    except asyncio.TimeoutError:
        await message.answer("⏰ 55 soniya ichida yuklanmadi. Havola juda katta yoki bloklanган.")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")
    finally:
        await wait_msg.delete()
        if os.path.exists(output): os.remove(output)
        await state.clear()

@dp.message(F.text == "🔍 Shazam")
async def shazam_start(message: Message):
    await message.answer("❌ Shazam vaqtincha ishlamaydi (paket muammosi).")

def make_calc_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_b("🔢 Kalkulator", "c_mode_basic"), _b("🔬 Ilmiy", "c_mode_science")],
        [_b("💱 Valyuta", "c_open_currency"), _b("📏 Birliklar", "c_open_convert")],
        [_b("📜 Tarix", "c_history")],
    ])

@dp.message(F.text == "🧮 Kalkulator")
async def calc_open(message: Message):
    user_calc_expr[message.from_user.id] = ""
    await message.answer(
        "🧮 <b>CalcBot</b>\n\nQuyidagi tugmalardan birini tanlang:",
        parse_mode="HTML", reply_markup=make_calc_menu_kb()
    )

@dp.callback_query(F.data.startswith("c_"))
async def calc_callback(query: CallbackQuery):
    uid = query.from_user.id
    action = query.data[2:]
    expr = user_calc_expr.get(uid, "")

    # --- Navigatsiya ---
    if action == "close":
        await query.message.delete()
        await query.answer()
        return

    if action == "menu":
        user_calc_expr[uid] = ""
        await query.message.edit_text(
            "🧮 <b>CalcBot</b>\n\nQuyidagi tugmalardan birini tanlang:",
            parse_mode="HTML", reply_markup=make_calc_menu_kb())
        await query.answer(); return

    if action == "mode_basic":
        user_calc_expr[uid] = expr
        await query.message.edit_text(
            f"🧮 <b>Kalkulator</b>\n\n<code>{expr or '0'}</code>",
            parse_mode="HTML", reply_markup=make_calc_kb("basic"))
        await query.answer(); return

    if action == "mode_science":
        user_calc_expr[uid] = expr
        await query.message.edit_text(
            f"🔬 <b>Ilmiy kalkulator</b>\n\n<code>{expr or '0'}</code>",
            parse_mode="HTML", reply_markup=make_calc_kb("science"))
        await query.answer(); return

    if action == "history":
        hist = user_calc_history.get(uid, [])
        if not hist:
            text = "📜 <b>Tarix</b>\n\nHali hisoblashlar yo'q."
        else:
            lines = [f"{i+1}. <code>{e}</code> = <b>{r}</b>" for i, (e, r) in enumerate(hist)]
            text = "📜 <b>Oxirgi hisoblashlar:</b>\n\n" + "\n".join(lines)
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=make_history_kb())
        await query.answer(); return

    if action == "clear_history":
        user_calc_history[uid] = []
        await query.message.edit_text("🗑 <b>Tarix tozalandi!</b>",
            parse_mode="HTML", reply_markup=make_history_kb())
        await query.answer(); return

    if action == "open_currency":
        await query.message.edit_text(
            "💱 <b>Valyuta Konvertori</b>\n\nYo'nalishni tanlang:",
            parse_mode="HTML", reply_markup=make_currency_kb())
        await query.answer(); return

    if action == "open_convert":
        await query.message.edit_text(
            "📏 <b>Birlik O'zgartirish</b>\n\nYo'nalishni tanlang:",
            parse_mode="HTML", reply_markup=make_convert_kb())
        await query.answer(); return

    if action.startswith("cur_"):
        parts = action[4:].split("_")
        from_cur, to_cur = parts[0], parts[1]
        user_calc_awaiting[uid] = {"type": "currency", "from": from_cur, "to": to_cur}
        await query.message.edit_text(
            f"💱 <b>{from_cur} → {to_cur}</b>\n\nMiqdorni yozing (masalan: <code>100</code>):",
            parse_mode="HTML")
        await query.answer(); return

    if action.startswith("conv_"):
        conv_type = action[5:]
        user_calc_awaiting[uid] = {"type": "convert", "conv_type": conv_type}
        labels = {"km_mi": "km ↔ mi", "kg_lb": "kg ↔ lb", "c_f": "°C ↔ °F", "m_ft": "m ↔ ft"}
        await query.message.edit_text(
            f"📏 <b>{labels.get(conv_type, conv_type)}</b>\n\nMiqdorni yozing (masalan: <code>100</code>):",
            parse_mode="HTML")
        await query.answer(); return

    # --- Kalkulator tugmalari ---
    if action == "C":
        expr = ""
    elif action == "back":
        expr = expr[:-1]
    elif action == "=":
        if not expr:
            await query.answer(); return
        try:
            result = safe_calc(expr)
            formatted = format_result(result)
            hist = user_calc_history.get(uid, [])
            hist.append((expr, formatted))
            if len(hist) > 10: hist = hist[-10:]
            user_calc_history[uid] = hist
            user_calc_expr[uid] = str(result)
            await query.message.edit_text(
                f"🧮 <b>Natija</b>\n\n<code>{expr}</code>\n━━━━━━━━━━━━━\n✅ <b>{formatted}</b>",
                parse_mode="HTML", reply_markup=make_result_kb())
        except CalcError as e:
            await query.answer(f"❌ {str(e)}", show_alert=True)
        await query.answer(); return
    elif action == "^2":
        expr += "^2"
    elif action == "1/x":
        expr = f"1/({expr})" if expr else "1/"
    else:
        expr += action

    user_calc_expr[uid] = expr
    sci_funcs = ["sin", "cos", "tan", "log", "ln", "sqrt", "π"]
    mode = "science" if any(f in expr for f in sci_funcs) else "basic"
    title = "🔬 <b>Ilmiy kalkulator</b>" if mode == "science" else "🧮 <b>Kalkulator</b>"
    try:
        await query.message.edit_text(
            f"{title}\n\n<code>{expr or '0'}</code>",
            parse_mode="HTML", reply_markup=make_calc_kb(mode))
    except: pass
    await query.answer()

@dp.message(F.text == "🤖 AI Suhbat")
async def chat_start(message: Message, state: FSMContext):
    await state.set_state(MixState.waiting_chat)
    await state.update_data(history=[])
    await message.answer(
        "🤖 <b>AI Suhbat</b>\n\n"
        "Menga istalgan savol bering — javob beraman!\n"
        "O'zbek, Rus yoki Ingliz tilida yozishingiz mumkin.\n\n"
        "🗑 <b>Suhbatni tozala</b> — yangi mavzu boshlash\n"
        "🔙 <b>Chiqish</b> — menyuga qaytish",
        parse_mode="HTML", reply_markup=chat_keyboard
    )

@dp.message(MixState.waiting_chat, F.text == "🔙 Chiqish")
async def chat_exit(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_keyboard)

@dp.message(MixState.waiting_chat, F.text == "🗑 Suhbatni tozala")
async def chat_clear(message: Message, state: FSMContext):
    await state.update_data(history=[])
    await message.answer("✅ Suhbat tozalandi. Yangi savol bering.", reply_markup=chat_keyboard)

@dp.message(MixState.waiting_chat, F.text)
async def chat_handle(message: Message, state: FSMContext):
    from groq import AsyncGroq
    groq_key = os.getenv("GROQ_KEY")
    if not groq_key:
        return await message.answer("❌ Groq API kalit topilmadi.")

    data = await state.get_data()
    history = data.get("history", [])

    history.append({"role": "user", "content": message.text})
    if len(history) > 20:
        history = history[-20:]

    wait_msg = await message.answer("⏳ Javob tayyorlanmoqda...")
    try:
        client = AsyncGroq(api_key=groq_key)
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": (
                        "Sen Sadoon AI — aqlli va do'stona yordamchi. "
                        "O'zbek, Rus va Ingliz tillarini bilasan. "
                        "Foydalanuvchi qaysi tilda yozsa, o'sha tilda javob ber. "
                        "Qisqa, aniq va foydali javob ber."
                    )}
                ] + history,
                max_tokens=1000,
                temperature=0.7,
            ), timeout=30
        )
        reply = response.choices[0].message.content
        history.append({"role": "assistant", "content": reply})
        await state.update_data(history=history)
        try:
            await wait_msg.delete()
        except: pass
        await message.answer(reply, reply_markup=chat_keyboard)
    except asyncio.TimeoutError:
        await wait_msg.edit_text("⏰ Javob kelmadi. Qaytadan urinib ko'ring.")
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik: {str(e)[:200]}")

@dp.message(F.text == "🎬 Klip Yaratish")
async def clip_start(message: Message, state: FSMContext):
    await message.answer("🖼 Rasm yuboring.")
    await state.set_state(MixState.waiting_clip_photo)

@dp.message(MixState.waiting_clip_photo, F.photo)
async def handle_clip_photo(message: Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("🎵 Audio yuboring.")
    await state.set_state(MixState.waiting_clip_audio)

@dp.message(MixState.waiting_clip_audio, F.audio)
async def handle_clip_audio(message: Message, state: FSMContext):
    data = await state.get_data()
    wait_msg = await message.answer("🎬 Tayyorlanmoqda...")
    p_path = f"temp/p_{uuid.uuid4()}.jpg"
    a_path = f"temp/a_{uuid.uuid4()}.mp3"
    v_path = f"output/v_{uuid.uuid4()}.mp4"
    try:
        pfile = await bot.get_file(data['photo'])
        await bot.download_file(pfile.file_path, p_path)
        afile = await bot.get_file(message.audio.file_id)
        await bot.download_file(afile.file_path, a_path)
        if await asyncio.wait_for(mixer.mix_image_audio(p_path, a_path, v_path), timeout=120):
            await message.answer_video(video=FSInputFile(v_path))
            db.log_stats(message.from_user.id, "mix")
        else:
            await message.answer("❌ Klip yaratishda xatolik.")
    except asyncio.TimeoutError:
        await message.answer("⏰ Vaqt tugadi (120s). Qisqaroq audio sinab ko'ring.")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")
    finally:
        await wait_msg.delete()
        for f in [p_path, a_path, v_path]:
            if os.path.exists(f): os.remove(f)
        await state.clear()

@dp.message(F.text == "✍️ Takliflar")
async def feedback_start(message: Message, state: FSMContext):
    await message.answer("✍️ Taklifingizni yozing.")
    await state.set_state(MixState.waiting_feedback)

@dp.message(MixState.waiting_feedback, F.text)
async def handle_feedback(message: Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"📩 Taklif: {message.from_user.full_name}\n{message.text}")
    await message.answer("✅ Yuborildi. Rahmat!")
    await state.clear()

# ═══════════════════════════════════════════
# ✍️ SMM STUDIO
# ═══════════════════════════════════════════

SMM_PROMPTS = {
    "smm_post": smm_post.SYSTEM_PROMPT,
    "smm_reels": smm_reels.SYSTEM_PROMPT,
    "smm_plan": smm_plan.SYSTEM_PROMPT,
    "smm_hashtag": smm_hashtag.SYSTEM_PROMPT,
    "smm_caption": smm_caption.SYSTEM_PROMPT,
    "smm_strategy": smm_strategy.SYSTEM_PROMPT,
}

async def ask_openai_smm(system_prompt: str, user_message: str) -> str:
    if not openai_client:
        return None
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=SMM_MAX_TOKENS,
            temperature=SMM_TEMPERATURE,
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"OpenAI xato: {e}")
        return None

async def smm_process(message: Message, state: FSMContext, mode: str):
    uid = message.from_user.id
    allowed, used, daily_limit, is_prem = db.try_smm(uid, SMM_FREE_DAILY, SMM_PREMIUM_DAILY)
    if not allowed:
        await message.answer(
            f"⚠️ <b>Kunlik limit tugadi!</b>\n\n"
            f"📝 Bugun {used}/{daily_limit} ta so'rov ishlatildi.\n\n"
            f"💎 Ko'proq ishlash uchun Plus oling: {PAYMENT_ADMIN}",
            parse_mode="HTML", reply_markup=paid_keyboard
        )
        await state.clear()
        return

    wait_msg = await message.answer("⏳ SMM AI ishlamoqda...")
    result = await ask_openai_smm(SMM_PROMPTS[mode], message.text)
    try:
        await wait_msg.delete()
    except:
        pass

    if result is None:
        await message.answer("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.", reply_markup=smm_keyboard)
    else:
        db.log_stats(uid, mode)
        if len(result) > 4000:
            for part in [result[i:i+4000] for i in range(0, len(result), 4000)]:
                await message.answer(part)
        else:
            await message.answer(result)
        remaining = max(0, daily_limit - used)
        if is_prem:
            footer = f"💎 Plus: {remaining}/{daily_limit} ta so'rov qoldi"
        else:
            footer = f"📊 Qolgan bepul so'rovlar: {remaining}/{daily_limit}"
        await message.answer(footer, reply_markup=smm_keyboard)
    await state.clear()

@dp.message(F.text == "✍️ SMM Studio")
async def smm_menu(message: Message):
    await message.answer("✍️ <b>SMM Studio</b>\n\nQaysi xizmatdan foydalanmoqchisiz?", reply_markup=smm_keyboard, parse_mode="HTML")

@dp.message(F.text == "🔙 Orqaga")
async def smm_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_keyboard)

@dp.message(F.text == "📝 Post yozish")
async def smm_post_start(message: Message, state: FSMContext):
    await message.answer("📝 Qaysi mavzuda post yozay?\n\n<i>Misol: Go'zallik saloni uchun aktsiya posti</i>", parse_mode="HTML")
    await state.set_state(MixState.smm_post)

@dp.message(MixState.smm_post, F.text)
async def smm_post_handle(message: Message, state: FSMContext):
    await smm_process(message, state, "smm_post")

@dp.message(F.text == "🎬 Reels ssenariy")
async def smm_reels_start(message: Message, state: FSMContext):
    await message.answer("🎬 Qanday mavzuda reels ssenariy yozay?\n\n<i>Misol: Kafe uchun 'bir kunim' formatida reels</i>", parse_mode="HTML")
    await state.set_state(MixState.smm_reels)

@dp.message(MixState.smm_reels, F.text)
async def smm_reels_handle(message: Message, state: FSMContext):
    await smm_process(message, state, "smm_reels")

@dp.message(F.text == "📅 Kontent plan")
async def smm_plan_start(message: Message, state: FSMContext):
    await message.answer("📅 Qaysi nisha uchun 30 kunlik plan tuzay?\n\n<i>Misol: Online kiyim do'koni</i>", parse_mode="HTML")
    await state.set_state(MixState.smm_plan)

@dp.message(MixState.smm_plan, F.text)
async def smm_plan_handle(message: Message, state: FSMContext):
    await smm_process(message, state, "smm_plan")

@dp.message(F.text == "#️⃣ Hashtag")
async def smm_hashtag_start(message: Message, state: FSMContext):
    await message.answer("#️⃣ Qaysi mavzu uchun hashtag kerak?\n\n<i>Misol: Fitness va sport ozuqa</i>", parse_mode="HTML")
    await state.set_state(MixState.smm_hashtag)

@dp.message(MixState.smm_hashtag, F.text)
async def smm_hashtag_handle(message: Message, state: FSMContext):
    await smm_process(message, state, "smm_hashtag")

@dp.message(F.text == "💬 Caption")
async def smm_caption_start(message: Message, state: FSMContext):
    await message.answer("💬 Rasm tavsifi yoki mavzuni yozing:\n\n<i>Misol: Yangi kolleksiya keldi, stilist fotosessiya</i>", parse_mode="HTML")
    await state.set_state(MixState.smm_caption)

@dp.message(MixState.smm_caption, F.text)
async def smm_caption_handle(message: Message, state: FSMContext):
    await smm_process(message, state, "smm_caption")

@dp.message(F.text == "📊 Strategiya")
async def smm_strategy_start(message: Message, state: FSMContext):
    await message.answer("📊 Biznes turingiz va maqsadingizni yozing:\n\n<i>Misol: Stomatologiya klinikasi, Instagram orqali mijoz jalb qilish</i>", parse_mode="HTML")
    await state.set_state(MixState.smm_strategy)

@dp.message(MixState.smm_strategy, F.text)
async def smm_strategy_handle(message: Message, state: FSMContext):
    await smm_process(message, state, "smm_strategy")


@dp.message(F.text)
async def calc_awaiting_handler(message: Message):
    uid = message.from_user.id
    awaiting = user_calc_awaiting.get(uid)
    if not awaiting:
        await message.answer("Asosiy menyu:", reply_markup=main_keyboard)
        return
    user_calc_awaiting.pop(uid, None)
    text = message.text.strip().replace(",", "").replace(" ", "")
    try:
        amount = float(text)
    except ValueError:
        await message.answer("❌ Raqam kiriting (masalan: 100)", reply_markup=make_currency_kb())
        return

    if awaiting["type"] == "currency":
        try:
            result = await convert_currency(amount, awaiting["from"], awaiting["to"])
            await message.answer(
                f"💱 <b>Valyuta konvertatsiyasi</b>\n\n"
                f"<code>{amount:,.2f} {awaiting['from']}</code>\n"
                f"━━━━━━━━━━━━━\n"
                f"✅ <b>{result:,.2f} {awaiting['to']}</b>",
                parse_mode="HTML", reply_markup=make_result_kb())
        except Exception as e:
            await message.answer(f"❌ Xato: {e}", reply_markup=make_currency_kb())

    elif awaiting["type"] == "convert":
        try:
            result = convert_unit(amount, awaiting["conv_type"])
            await message.answer(result, parse_mode="HTML", reply_markup=make_result_kb())
        except Exception as e:
            await message.answer(f"❌ Xato: {e}", reply_markup=make_convert_kb())

@dp.message()
async def echo(message: Message):
    await message.answer("Asosiy menyu:", reply_markup=main_keyboard)

def extract_url(text: str):
    from urllib.parse import urlparse
    urls = re.findall(r'https?://[^\s]+', text)
    for url in urls:
        url = url.strip('.,()!?*')
        try:
            parsed = urlparse(url)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                return url
        except:
            continue
    return None

async def main():
    os.makedirs("temp", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
