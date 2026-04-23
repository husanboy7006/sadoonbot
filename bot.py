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
            # Direct IP for Telegram (DC4)
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

if not TOKEN:
    print("❌ ERROR: Telegram BOT_TOKEN topilmadi!")
    exit(1)

try:
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
    
    model = genai.GenerativeModel("gemini-1.5-flash")
    model_cgi = genai.GenerativeModel("gemini-1.5-flash")
    
    db = Database()
    
    # --- ADVANCED SESSION FOR HUGGING FACE ---
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiohttp import TCPConnector
    
    # Connector settings
    connector = TCPConnector(
        family=socket.AF_INET, 
        verify_ssl=False, 
        use_dns_cache=True
    )
    
    # Timeout settings
    timeout = aiohttp.ClientTimeout(total=60, connect=30, sock_read=30)
    session = AiohttpSession(connector=connector, timeout=timeout)
    
    bot = Bot(token=TOKEN, session=session)
    dp = Dispatcher(storage=MemoryStorage())
except Exception as e:
    print(f"❌ Initialization Error: {e}")
    exit(1)

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
❗ MUHIM: Siz PROMPT yozmaysiz, siz FINAL RASM yaratasiz. Dizayner kabi fikrlaysiz.
🌐 TIL: FAQAT O'ZBEK TILIDA.
"""

# --- HANDLERS ---
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
    text = (
        "🎨 **Vibe tanlang:**\n1️⃣ Luxury, 2️⃣ Fresh, 3️⃣ Dark, 4️⃣ Minimal, 5️⃣ Energetic\n\n"
        "📐 **Platforma tanlang:**\n1️⃣ Instagram, 2️⃣ Story, 3️⃣ Banner, 4️⃣ Poster\n\n"
        "✍️ Misol: `1 2` (Luxury vibe, Story platforma)"
    )
    await message.answer(text, parse_mode="Markdown")
    await state.set_state(MixState.waiting_for_cgi_choices)

@dp.message(MixState.waiting_for_cgi_choices, F.text)
async def handle_cgi_final(message: Message, state: FSMContext):
    data = await state.get_data()
    choices = message.text.split()
    if len(choices) < 2:
        return await message.answer("Iltimos, ikkita raqamni kiriting. Misol: `1 2`")
    
    vibe_map = {"1":"Luxury", "2":"Fresh", "3":"Dark", "4":"Minimal", "5":"Energetic"}
    plat_map = {"1":"Instagram", "2":"Story", "3":"Banner", "4":"Poster"}
    vibe = vibe_map.get(choices[0], "Luxury")
    plat = plat_map.get(choices[1], "Instagram")
    
    wait_msg = await message.answer("⏳ **CGI Artist ishlamoqda...**")
    
    try:
        file = await bot.get_file(data.get("cgi_photo"))
        file_path = file.file_path
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as r:
                if r.status != 200:
                    return await message.answer("❌ Rasmni yuklab bo'lmadi.")
                img_data = await r.read()

        await state.clear()

        # 1. Try Nano Banana (Paid)
        try:
            full_prompt = f"{CGI_PROMPT}\nVibe: {vibe}\nFormat: {plat}\nMahsulotni saqlab qolgan holda super-realistik reklama yarat."
            response = await asyncio.wait_for(
                model_cgi.generate_content_async([full_prompt, {"mime_type": "image/jpeg", "data": img_data}]),
                timeout=90
            )
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'inline_data'):
                        await message.answer_photo(
                            photo=BufferedInputFile(part.inline_data.data, filename="cgi.jpg"),
                            caption="💎 **Premium CGI (Nano Banana)**"
                        )
                        return await finish_cgi(message, wait_msg)
        except Exception as e:
            print(f"Nano failed: {e}")

        # 2. Smart Fallback (Flux + Vision)
        await message.answer("⏳ Premium limit kutmoqda... 'Smart Fallback' rejimi ishga tushdi.")
        try:
            vision_query = "Ushbu rasmdagi asosiy mahsulotni bitta so'z bilan inglizcha ayting (masalan: Cola, Soap, Perfume)."
            v_res = model.generate_content([vision_query, {"mime_type": "image/jpeg", "data": img_data}])
            p_name = v_res.text.strip() if v_res.text else "Product"
            
            f_prompt = f"Professional studio product photography of {p_name}, {vibe} style, {plat} aspect ratio, cinematic lighting, high resolution, 8k"
            flux_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(f_prompt)}?width=1024&height=1024&nologo=true"
            
            async with aiohttp.ClientSession() as s:
                async with s.get(flux_url) as fr:
                    if fr.status == 200:
                        await message.answer_photo(
                            photo=BufferedInputFile(await fr.read(), filename="cgi_flux.jpg"),
                            caption=f"✅ **Smart Fallback: {p_name}**\n(Premium limit ochilguncha vaqtunchalik rejim)"
                        )
                        return await finish_cgi(message, wait_msg)
        except Exception as fe:
            await message.answer(f"❌ Har ikkala tizimda xatolik: {fe}")

    except Exception as global_e:
        await message.answer(f"❌ Xato: {global_e}")
    finally:
        try: await wait_msg.delete()
        except: pass

async def finish_cgi(message, wait_msg):
    if message.from_user.id != ADMIN_ID:
        db.update_balance(message.from_user.id, -1)
    db.log_stats(message.from_user.id, "cgi")
    await message.answer("Bajarildi! Menyu:", reply_markup=main_keyboard)

@dp.message(F.text == "🌐 Tilmoch AI")
async def trans_start(message: Message, state: FSMContext):
    await message.answer("✍️ Tarjima qilinadigan xabarni yuboring.")
    await state.set_state(MixState.waiting_translate)

@dp.message(MixState.waiting_translate, F.text)
async def handle_translate(message: Message, state: FSMContext):
    try:
        res = model.generate_content(f"Siz professional tarjimon va tilshunosiz. Matnni tarjima qiling va tushuntiring: {message.text}")
        await message.answer(res.text)
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")
    await state.clear()

@dp.message(F.text == "📥 Yuklab olish")
async def download_start(message: Message, state: FSMContext):
    await message.answer("🔗 **TikTok, Instagram, YouTube yoki Pinterest** havolasini yuboring.")
    await state.set_state(MixState.waiting_download)

@dp.message(MixState.waiting_download, F.text)
async def handle_download(message: Message, state: FSMContext):
    url = extract_url(message.text)
    if not url:
        return await message.answer("❌ Iltimos, to'g'ri havola yuboring.")
    
    wait_msg = await message.answer("⏳ **Yuklanmoqda...**")
    uid = str(uuid.uuid4())[:8]
    output_v = f"temp/v_{uid}.mp4"
    output_a = f"temp/a_{uid}.mp3"

    try:
        success = await mixer.download_video(url, output_v)
        if success:
            await message.answer_video(video=FSInputFile(output_v), caption="✅ @sadoon_ai_bot orqali yuklab olindi.")
        else:
            success_a = await mixer.download_audio(url, output_a)
            if success_a:
                await message.answer_audio(audio=FSInputFile(output_a), caption="🎵 Audio yuklab olindi.")
            else:
                await message.answer("❌ Yuklab bo'lmadi. Havola noto'g'ri yoki bot bloklangan.")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")
    finally:
        await wait_msg.delete()
        if os.path.exists(output_v): os.remove(output_v)
        if os.path.exists(output_a): os.remove(output_a)
        await state.clear()

@dp.message(F.text == "🔍 Shazam")
async def shazam_start(message: Message, state: FSMContext):
    await message.answer("🎧 Musiqa parchasini (ovozli xabar, audio yoki video) yuboring.")
    await state.set_state(MixState.waiting_shazam)

@dp.message(MixState.waiting_shazam, F.audio | F.voice | F.video)
async def handle_shazam(message: Message, state: FSMContext):
    wait_msg = await message.answer("🔍 **Musiqa qidirilmoqda...**")
    file_id = None
    if message.audio: file_id = message.audio.file_id
    elif message.voice: file_id = message.voice.file_id
    elif message.video: file_id = message.video.file_id

    file = await bot.get_file(file_id)
    temp_path = f"temp/shz_{uuid.uuid4()}.mp3"
    await bot.download_file(file.file_path, temp_path)

    try:
        info = await mixer.identify_music(temp_path)
        if info:
            text = f"✅ **Topildi!**\n\n🎵 **Nomi:** {info['title']}\n👤 **Ijrochi:** {info['subtitle']}\n\n🔗 [Shazam Havolasi]({info['shazam_url']})"
            if info['image']:
                await message.answer_photo(photo=info['image'], caption=text, parse_mode="Markdown")
            else:
                await message.answer(text, parse_mode="Markdown")
        else:
            await message.answer("❌ Afsuski, musiqa topilmadi.")
    except Exception as e:
        await message.answer(f"❌ Shazam hatosi: {e}")
    finally:
        await wait_msg.delete()
        if os.path.exists(temp_path): os.remove(temp_path)
        await state.clear()

@dp.message(F.text == "🎬 Klip Yaratish (V3) (🖼️ rasm + 🎵 musiqa)")
async def clip_start(message: Message, state: FSMContext):
    await message.answer("🖼 **1-qadam:** Klip uchun rasm yuboring.")
    await state.set_state(MixState.waiting_clip_photo)

@dp.message(MixState.waiting_clip_photo, F.photo)
async def handle_clip_photo(message: Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("🎵 **2-qadam:** Klip uchun audio (mp3) yuboring.")
    await state.set_state(MixState.waiting_clip_audio)

@dp.message(MixState.waiting_clip_audio, F.audio)
async def handle_clip_audio(message: Message, state: FSMContext):
    data = await state.get_data()
    wait_msg = await message.answer("🎬 **Klip tayyorlanmoqda...**")
    
    uid = str(uuid.uuid4())[:8]
    p_path = f"temp/p_{uid}.jpg"
    a_path = f"temp/a_{uid}.mp3"
    v_path = f"output/clip_{uid}.mp4"

    try:
        photo = await bot.get_file(data['photo'])
        await bot.download_file(photo.file_path, p_path)
        
        audio = await bot.get_file(message.audio.file_id)
        await bot.download_file(audio.file_path, a_path)

        success = await mixer.mix_image_audio(p_path, a_path, v_path)
        if success:
            await message.answer_video(video=FSInputFile(v_path), caption="🎬 Klip tayyor! @sadoon_ai_bot")
        else:
            await message.answer("❌ Klip yaratishda xatolik yub berdi.")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")
    finally:
        await wait_msg.delete()
        for f in [p_path, a_path, v_path]:
            if os.path.exists(f): os.remove(f)
        await state.clear()

@dp.message(F.text == "✍️ Takliflar")
async def feedback_start(message: Message, state: FSMContext):
    await message.answer("✍️ Botni yaxshilash bo'yicha taklifingizni yozib qoldiring.")
    await state.set_state(MixState.waiting_feedback)

@dp.message(MixState.waiting_feedback, F.text)
async def handle_feedback(message: Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"📩 **Yangi taklif:**\nKimdan: {message.from_user.full_name}\nID: {message.from_user.id}\n\nMatn: {message.text}")
    await message.answer("✅ Taklifingiz adminlarga yuborildi. Rahmat!")
    await state.clear()

@dp.message(F.text == "💰 To'ldirish")
async def refill_start(message: Message):
    await message.answer(f"💰 **Balansni to'ldirish uchun adminga murojaat qiling:**\nID: `{message.from_user.id}`\nAdmin: @husanjon007", parse_mode="Markdown")

def extract_url(text: str):
    import re
    urls = re.findall(r'http[s]?://[^\s]+', text)
    return urls[0].strip('.,()!?*') if urls else None

@dp.message()
async def echo(message: Message):
    await message.answer("Asosiy menyu:", reply_markup=main_keyboard)

async def start_app():
    print("[*] Bot starting sequence initiated...")
    if not os.path.exists("temp"): os.makedirs("temp")
    if not os.path.exists("output"): os.makedirs("output")
    
    print("[*] Initializing database...")
    db.init_db()
    
    print("[*] Starting polling... (If this is the last message, polling has started)")
    # Webhookni o'chirishni vaqtincha o'chirib turamiz (Hanging muammosi uchun)
    # await bot.delete_webhook(drop_pending_updates=True) 
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"[!] Polling Error: {e}")

if __name__ == "__main__":
    asyncio.run(start_app())
