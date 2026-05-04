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
from google.genai import types as genai_types
from database import Database
import mixer

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)

# --- CONFIG ---
TOKEN = os.getenv("HF_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("API_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY") or os.getenv("GEMINI_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5614682028"))
WEBHOOK_PATH = f"/webhook/{TOKEN}"
BASE_URL = os.getenv("BASE_URL", "https://husanjon007-sadoon-api.hf.space")

if not TOKEN:
    print("❌ ERROR: Telegram BOT_TOKEN topilmadi!")
    exit(1)

gemini_client = None
if GEMINI_KEY:
    gemini_client = google_genai.Client(api_key=GEMINI_KEY)

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

# --- KEYBOARDS ---
main_keyboard = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="🎬 Klip Yaratish (V3) (🖼️ rasm + 🎵 musiqa)")],
        [types.KeyboardButton(text="🚀 CGI Product Artist (Premium v2)")],
        [types.KeyboardButton(text="📥 Yuklab olish"), types.KeyboardButton(text="🔍 Shazam")],
        [types.KeyboardButton(text="🌐 Tilmoch AI"), types.KeyboardButton(text="💎 Balans")],
        [types.KeyboardButton(text="✍️ Takliflar"), types.KeyboardButton(text="💰 To'ldirish")]
    ],
    resize_keyboard=True
)

# --- PROMPTS ---
CGI_PROMPT = """Siz dunyo darajasidagi AI Product Visualization Director, CGI artist va reklama creative direktorisiz.
❗ SIZNING VAZIFANGIZ: Foydalanuvchi yuborgan mahsulot asosida HIGH-END, cinematic reklama RASM yaratish.
🌐 TIL: FAQAT O'ZBEK TILIDA."""

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
    await state.update_data(cgi_photo=message.photo[-1].file_id)
    text = "🎨 Vibe: 1-Luxury 2-Fresh 3-Dark 4-Minimal 5-Energetic\n📐 Platforma: 1-Instagram 2-Story 3-Banner 4-Poster\nMisol: 1 2"
    await message.answer(text)
    await state.set_state(MixState.waiting_for_cgi_choices)

@dp.message(MixState.waiting_for_cgi_choices, F.text)
async def handle_cgi_final(message: Message, state: FSMContext):
    data = await state.get_data()
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
        file = await bot.get_file(data.get("cgi_photo"))
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
        async with aiohttp.ClientSession() as s:
            async with s.get(file_url) as r:
                img_data = await r.read()
        try:
            if gemini_client:
                resp = await asyncio.wait_for(
                    gemini_client.aio.models.generate_content(
                        model="gemini-1.5-flash",
                        contents=[f"{CGI_PROMPT}\nVibe:{vibe} Format:{plat}",
                                  genai_types.Part.from_bytes(data=img_data, mime_type="image/jpeg")]
                    ), timeout=90)
                if resp.candidates:
                    for part in resp.candidates[0].content.parts:
                        if hasattr(part, 'inline_data'):
                            await message.answer_photo(photo=BufferedInputFile(part.inline_data.data, filename="cgi.jpg"), caption="💎 Premium CGI")
                        if message.from_user.id != ADMIN_ID: db.update_balance(message.from_user.id, -1)
                        db.log_stats(message.from_user.id, "cgi")
                        return
        except Exception as e:
            print(f"CGI Gemini error: {e}")
        # Fallback
        f_prompt = f"product photography {vibe} style {plat}"
        flux_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(f_prompt)}?nologo=true"
        async with aiohttp.ClientSession() as s:
            async with s.get(flux_url) as fr:
                if fr.status == 200:
                    await message.answer_photo(photo=BufferedInputFile(await fr.read(), filename="cgi.jpg"), caption="✅ Smart Fallback")
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
        res = await gemini_client.aio.models.generate_content(
            model="gemini-1.5-flash",
            contents=f"Tarjima qiling: {message.text}"
        )
        await message.answer(res.text)
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
        if await mixer.download_video(url, output):
            await message.answer_video(video=FSInputFile(output))
        else:
            await message.answer("❌ Yuklab bo'lmadi.")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")
    finally:
        await wait_msg.delete()
        if os.path.exists(output): os.remove(output)
        await state.clear()

@dp.message(F.text == "🔍 Shazam")
async def shazam_start(message: Message, state: FSMContext):
    await message.answer("🎧 Audio/Video yuboring.")
    await state.set_state(MixState.waiting_shazam)

@dp.message(MixState.waiting_shazam, F.audio | F.voice | F.video)
async def handle_shazam(message: Message, state: FSMContext):
    wait_msg = await message.answer("🔍 Qidirilmoqda...")
    temp = f"temp/shz_{uuid.uuid4()}.mp3"
    try:
        fid = message.audio.file_id if message.audio else (message.voice.file_id if message.voice else message.video.file_id)
        file = await bot.get_file(fid)
        await bot.download_file(file.file_path, temp)
        info = await mixer.identify_music(temp)
        if info:
            text = f"✅ Topildi!\n🎵 {info['title']}\n👤 {info['subtitle']}"
            await message.answer(text)
        else:
            await message.answer("❌ Topilmadi.")
    except Exception as e:
        await message.answer(f"❌ Shazam hatosi: {e}")
    finally:
        await wait_msg.delete()
        if os.path.exists(temp): os.remove(temp)
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
        if await mixer.mix_image_audio(p_path, a_path, v_path):
            await message.answer_video(video=FSInputFile(v_path))
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

@dp.message()
async def echo(message: Message):
    await message.answer("Asosiy menyu:", reply_markup=main_keyboard)

def extract_url(text: str):
    urls = re.findall(r'http[s]?://[^\s]+', text)
    return urls[0].strip('.,()!?*') if urls else None

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
