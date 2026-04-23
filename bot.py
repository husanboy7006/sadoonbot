import logging
import asyncio
import os
import aiohttp
import socket
import ssl
import json
import urllib.request
import shutil
import uuid
import urllib.parse
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import google.generativeai as genai
from database import Database
import mixer

# --- UNIVERSAL DNS PATCH FOR HUGGING FACE ---
def apply_dns_patch():
    old_getaddrinfo = socket.getaddrinfo
    def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if host == "api.telegram.org":
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('149.154.167.220', port))]
        return old_getaddrinfo(host, port, family, type, proto, flags)
    socket.getaddrinfo = patched_getaddrinfo

apply_dns_patch()

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)

# --- CONFIG ---
TOKEN = os.getenv("HF_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("API_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY") or os.getenv("GEMINI_API_KEY")
ADMIN_ID = 5614682028

db = Database()
bot = None
dp = None

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
CGI_PROMPT = """
Siz dunyo darajasidagi AI Product Visualization Director, CGI artist va reklama creative direktorisiz.
❗ SIZNING VAZIFANGIZ: Foydalanuvchi yuborgan mahsulot asosida HIGH-END, cinematic reklama RASM yaratish.
🌐 TIL: FAQAT O'ZBEK TILIDA.
"""

# --- HANDLERS (Moved after initialization) ---

def register_handlers(dp):
    @dp.message(Command("start"))
    async def start(message: Message):
        print(f"[*] /start received from {message.from_user.id}")
        try:
            db.add_user(message.from_user.id, message.from_user.full_name)
        except Exception as e:
            print(f"[!] Database Error in /start: {e}")
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
        text = "🎨 **Vibe tanlang:**\n1️⃣ Luxury, 2️⃣ Fresh, 3️⃣ Dark, 4️⃣ Minimal, 5️⃣ Energetic\n\n📐 **Platforma tanlang:**\n1️⃣ Instagram, 2️⃣ Story, 3️⃣ Banner, 4️⃣ Poster"
        await message.answer(text, parse_mode="Markdown")
        await state.set_state(MixState.waiting_for_cgi_choices)

    @dp.message(MixState.waiting_for_cgi_choices, F.text)
    async def handle_cgi_final(message: Message, state: FSMContext):
        data = await state.get_data()
        choices = message.text.split()
        if len(choices) < 2: return await message.answer("Iltimos, ikkita raqamni kiriting. Misol: `1 2`")
        
        vibe_map = {"1":"Luxury", "2":"Fresh", "3":"Dark", "4":"Minimal", "5":"Energetic"}
        plat_map = {"1":"Instagram", "2":"Story", "3":"Banner", "4":"Poster"}
        vibe = vibe_map.get(choices[0], "Luxury")
        plat = plat_map.get(choices[1], "Instagram")
        
        wait_msg = await message.answer("⏳ **CGI Artist ishlamoqda...**")
        try:
            file = await bot.get_file(data.get("cgi_photo"))
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as r:
                    img_data = await r.read()
            
            # Gemini CGI Logic
            try:
                model_cgi = genai.GenerativeModel("gemini-1.5-flash")
                full_prompt = f"{CGI_PROMPT}\nVibe: {vibe}\nFormat: {plat}\nMahsulotni saqlab qolgan holda super-realistik reklama yarat."
                response = await asyncio.wait_for(model_cgi.generate_content_async([full_prompt, {"mime_type": "image/jpeg", "data": img_data}]), timeout=90)
                if response.candidates:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, 'inline_data'):
                            await message.answer_photo(photo=BufferedInputFile(part.inline_data.data, filename="cgi.jpg"), caption="💎 **Premium CGI**")
                            return await finish_cgi(message, wait_msg)
            except: pass
            
            # Fallback
            await message.answer("⏳ Smart Fallback ishlamoqda...")
            flux_url = f"https://image.pollinations.ai/prompt/product photography in {vibe} style, {plat}?nologo=true"
            async with aiohttp.ClientSession() as s:
                async with s.get(flux_url) as fr:
                    await message.answer_photo(photo=BufferedInputFile(await fr.read(), filename="cgi.jpg"), caption="✅ **Smart Fallback**")
                    await finish_cgi(message, wait_msg)
        except Exception as e: await message.answer(f"❌ Xato: {e}")
        finally: await wait_msg.delete()

    @dp.message(F.text == "🌐 Tilmoch AI")
    async def trans_start(message: Message, state: FSMContext):
        await message.answer("✍️ Tarjima qilinadigan xabarni yuboring.")
        await state.set_state(MixState.waiting_translate)

    @dp.message(MixState.waiting_translate, F.text)
    async def handle_translate(message: Message, state: FSMContext):
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            res = model.generate_content(f"Tarjima qiling: {message.text}")
            await message.answer(res.text)
        except Exception as e: await message.answer(f"❌ Xato: {e}")
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
            else: await message.answer("❌ Yuklab bo'lmadi.")
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
            if info: await message.answer(f"✅ Topildi: {info['title']} - {info['subtitle']}")
            else: await message.answer("❌ Topilmadi.")
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
        p_path, a_path, v_path = f"temp/p_{uuid.uuid4()}.jpg", f"temp/a_{uuid.uuid4()}.mp3", f"output/v_{uuid.uuid4()}.mp4"
        try:
            pfile = await bot.get_file(data['photo'])
            await bot.download_file(pfile.file_path, p_path)
            afile = await bot.get_file(message.audio.file_id)
            await bot.download_file(afile.file_path, a_path)
            if await mixer.mix_image_audio(p_path, a_path, v_path):
                await message.answer_video(video=FSInputFile(v_path))
        finally:
            await wait_msg.delete()
            for f in [p_path, a_path, v_path]:
                if os.path.exists(f): os.remove(f)
            await state.clear()

    @dp.message()
    async def echo(message: Message):
        await message.answer("Asosiy menyu:", reply_markup=main_keyboard)

async def finish_cgi(message, wait_msg):
    if message.from_user.id != ADMIN_ID: db.update_balance(message.from_user.id, -1)
    db.log_stats(message.from_user.id, "cgi")
    await message.answer("Bajarildi!", reply_markup=main_keyboard)

def extract_url(text: str):
    urls = re.findall(r'http[s]?://[^\s]+', text)
    return urls[0].strip('.,()!?*') if urls else None

import re

async def start_app():
    global bot, dp
    print("[*] Bot starting sequence initiated...")
    if not os.path.exists("temp"): os.makedirs("temp")
    if not os.path.exists("output"): os.makedirs("output")
    
    # Initialization INSIDE the loop
    from aiogram.client.session.aiohttp import AiohttpSession
    
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
    
    session = AiohttpSession()
    bot = Bot(token=TOKEN, session=session)
    dp = Dispatcher(storage=MemoryStorage())
    
    register_handlers(dp)
    
    print("[*] Starting polling...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"[!] Polling Error: {e}")

if __name__ == "__main__":
    asyncio.run(start_app())
