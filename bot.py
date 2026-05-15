import logging
import asyncio
import os
import aiohttp
import uuid
import urllib.parse
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile, BufferedInputFile
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
    waiting_for_cgi_photo = State()
    waiting_for_cgi_choices = State()
    waiting_translate = State()
    waiting_download = State()
    waiting_shazam = State()
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
main_keyboard = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="🎬 Klip Yaratish (V3) (🖼️ rasm + 🎵 musiqa)")],
        [types.KeyboardButton(text="🚀 CGI Product Artist (Premium v2)")],
        [types.KeyboardButton(text="📥 Yuklab olish"), types.KeyboardButton(text="🔍 Shazam")],
        [types.KeyboardButton(text="🌐 Tilmoch AI"), types.KeyboardButton(text="💎 Balans")],
        [types.KeyboardButton(text="✍️ SMM Studio")],
        [types.KeyboardButton(text="✍️ Takliflar"), types.KeyboardButton(text="💰 To'ldirish")]
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

@dp.message(F.text == "💎 Balans")
async def check_balance(message: Message):
    balance = db.get_balance(message.from_user.id)
    await message.answer(f"Sizning balansingiz: {balance} somoniy.\nID: `{message.from_user.id}`", parse_mode="Markdown")

@dp.message(F.text == "🚀 CGI Product Artist (Premium v2)")
async def cgi_start(message: Message, state: FSMContext):
    await message.answer("📸 Reklama qilmoqchi bo'lgan mahsulotingiz rasmini yuboring.")
    await state.set_state(MixState.waiting_for_cgi_photo)

@dp.message(MixState.waiting_for_cgi_photo, F.photo)
async def handle_cgi_photo(message: Message, state: FSMContext):
    text = "🎨 Vibe: 1-Luxury 2-Fresh 3-Dark 4-Minimal 5-Energetic\n📐 Platforma: 1-Instagram 2-Story 3-Banner 4-Poster\nMisol: 1 2"
    await message.answer(text)
    await state.set_state(MixState.waiting_for_cgi_choices)

@dp.message(MixState.waiting_for_cgi_choices, F.text)
async def handle_cgi_final(message: Message, state: FSMContext):
    choices = message.text.split()
    if len(choices) < 2:
        return await message.answer("Iltimos, ikkita raqam: 1 2")
    vibe_map = {"1":"Luxury","2":"Fresh","3":"Dark","4":"Minimal","5":"Energetic"}
    plat_map = {"1":"Instagram","2":"Story","3":"Banner","4":"Poster"}
    vibe = vibe_map.get(choices[0], "Luxury")
    plat = plat_map.get(choices[1], "Instagram")
    await state.clear()
    wait_msg = await message.answer("⏳ CGI Artist ishlamoqda...")
    try:
        f_prompt = f"product photography {vibe} style {plat}"
        flux_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(f_prompt)}?nologo=true"
        async with aiohttp.ClientSession() as s:
            async with s.get(flux_url) as fr:
                if fr.status == 200:
                    await message.answer_photo(photo=BufferedInputFile(await fr.read(), filename="cgi.jpg"), caption="✅ CGI")
                    if message.from_user.id != ADMIN_ID: db.update_balance(message.from_user.id, -1)
                    db.log_stats(message.from_user.id, "cgi")
                else:
                    await message.answer("❌ Rasm yaratib bo'lmadi.")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")
    finally:
        try: await wait_msg.delete()
        except: pass

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

@dp.message(MixState.waiting_shazam, F.audio | F.voice | F.video)
async def handle_shazam(message: Message, state: FSMContext):
    await message.answer("❌ Shazam vaqtincha ishlamaydi.")
    await state.clear()

@dp.message(F.text == "🎬 Klip Yaratish (V3) (🖼️ rasm + 🎵 musiqa)")
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
            max_tokens=5000,
            temperature=0.8,
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"OpenAI xato: {e}")
        return None

async def smm_process(message: Message, state: FSMContext, mode: str):
    balance = db.get_balance(message.from_user.id)
    if balance <= 0:
        await message.answer(
            "⚠️ Balansingiz tugagan!\n\n💰 To'ldirish uchun /start bosing va To'ldirish tugmasini tanlang.",
            reply_markup=main_keyboard
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
        db.update_balance(message.from_user.id, -1)
        db.log_stats(message.from_user.id, mode)
        remaining = db.get_balance(message.from_user.id)
        if len(result) > 4000:
            parts = [result[i:i+4000] for i in range(0, len(result), 4000)]
            for part in parts:
                await message.answer(part)
        else:
            await message.answer(result)
        await message.answer(f"📊 Qolgan balans: {remaining} ta", reply_markup=smm_keyboard)
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
