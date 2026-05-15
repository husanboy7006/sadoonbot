import logging
import asyncio
import os
import uuid
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
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
    # SMM states
    smm_post = State()
    smm_reels = State()
    smm_plan = State()
    smm_hashtag = State()
    smm_caption = State()
    smm_strategy = State()

# --- KEYBOARDS ---
SMM_FREE_DAILY = int(os.getenv("FREE_DAILY_LIMIT", "3"))
SMM_MAX_TOKENS = int(os.getenv("MAX_TOKENS", "5000"))
SMM_TEMPERATURE = float(os.getenv("TEMPERATURE", "0.8"))

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
        [types.KeyboardButton(text="🎬 Klip Yaratish")],
        [types.KeyboardButton(text="🔍 Shazam")],
        [types.KeyboardButton(text="🔙 Orqaga")]
    ],
    resize_keyboard=True
)

paid_keyboard = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="✍️ SMM Studio")],
        [types.KeyboardButton(text="💎 Premium olish"), types.KeyboardButton(text="📊 Mening limitim")],
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
    await message.answer(f"Xush kelibsiz, {message.from_user.full_name}! Sadoon AI botiga xush kelibsiz.", reply_markup=main_keyboard)

@dp.message(Command("stats"))
async def user_stats(message: Message):
    uid = message.from_user.id
    used = db.get_daily_smm(uid)
    prem = db.is_premium(uid)
    if prem:
        until = db.get_user_metadata(uid).get("premium_until", "")
        status = f"💎 Premium ({until} gacha)"
        limit_text = "Cheksiz ♾️"
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

@dp.message(F.text == "📊 Mening limitim")
async def check_limit(message: Message):
    uid = message.from_user.id
    used = db.get_daily_smm(uid)
    prem = db.is_premium(uid)
    if prem:
        until = db.get_user_metadata(uid).get("premium_until", "")
        await message.answer(
            f"💎 <b>Premium aktiv</b>\n\n📅 {until} gacha\n✅ Cheksiz SMM so'rovlar",
            parse_mode="HTML", reply_markup=paid_keyboard
        )
    else:
        remaining = max(0, SMM_FREE_DAILY - used)
        await message.answer(
            f"📊 <b>Kunlik limitingiz</b>\n\n"
            f"📝 SMM bugun: {used}/{SMM_FREE_DAILY} ta\n"
            f"🆓 Qoldi: {remaining} ta\n\n"
            f"💎 Cheksiz ishlash uchun Premium oling!",
            parse_mode="HTML", reply_markup=paid_keyboard
        )

@dp.message(F.text == "💎 Premium olish")
async def premium_start(message: Message):
    await message.answer(
        f"💎 <b>Premium Rejim</b>\n\n"
        f"✅ Cheksiz SMM so'rovlar (kunlik limitsiz)\n\n"
        f"💰 <b>Tariflar (1 oy):</b>\n"
        f"⭐ Starter: 29,000 so'm\n"
        f"💎 Pro: 79,000 so'm\n"
        f"👑 Biznes: 149,000 so'm\n\n"
        f"To'lov uchun adminga yozing: @husanjon007\n"
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
        info = f"💎 Premium aktiv ({until} gacha) — Cheksiz ♾️"
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
    try:
        if not gemini_client:
            return await message.answer("❌ AI sozlanmagan.")
        res = await asyncio.wait_for(
            gemini_client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"Siz professional tarjimon va tilshunosiz. Ushbu matnni tarjima qiling va qisqacha izoh bering: {message.text}"
            ), timeout=30)
        await message.answer(res.text)
        db.log_stats(message.from_user.id, "translate")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")
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

@dp.message(F.text == "💰 To'ldirish")
async def refill_start(message: Message):
    await message.answer(f"💰 Admin: @husanjon007\nID: `{message.from_user.id}`", parse_mode="Markdown")

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
    if not db.is_premium(uid):
        used = db.get_daily_smm(uid)
        if used >= SMM_FREE_DAILY:
            await message.answer(
                f"⚠️ <b>Kunlik limit tugadi!</b>\n\n"
                f"📝 Bugun {SMM_FREE_DAILY}/{SMM_FREE_DAILY} ta bepul so'rov ishlatildi.\n\n"
                f"💎 Cheksiz ishlash uchun Premium oling: @husanjon007",
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
        used = db.increment_daily_smm(uid)
        db.log_stats(uid, mode)
        if len(result) > 4000:
            for part in [result[i:i+4000] for i in range(0, len(result), 4000)]:
                await message.answer(part)
        else:
            await message.answer(result)
        if db.is_premium(uid):
            footer = "💎 Premium — Cheksiz so'rovlar ♾️"
        else:
            footer = f"📊 Qolgan bepul so'rovlar: {max(0, SMM_FREE_DAILY - used)}/{SMM_FREE_DAILY}"
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
