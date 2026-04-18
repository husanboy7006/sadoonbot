import logging
import asyncio
import os
import aiohttp
import socket
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import google.generativeai as genai
from database import Database

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)

# --- CONFIG ---
TOKEN = os.getenv("HF_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")
ADMIN_ID = 5614682028

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")
model_cgi = genai.GenerativeModel("gemini-1.5-flash") # Using flash for better stability

db = Database()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- DNS PATCH FOR HUGGING FACE ---
def dns_patch():
    orig_getaddrinfo = socket.getaddrinfo
    def patched_getaddrinfo(*args, **kwargs):
        if args[0] == 'api.telegram.org':
            return orig_getaddrinfo('149.154.167.220', *args[1:], **kwargs)
        return orig_getaddrinfo(*args, **kwargs)
    socket.getaddrinfo = patched_getaddrinfo

dns_patch()

# --- STATES ---
class MixState(StatesGroup):
    waiting_for_cgi_photo = State()
    waiting_for_cgi_choices = State()
    waiting_translate = State()

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
    db.add_user(message.from_user.id, message.from_user.full_name)
    await message.answer(f"Xush kelibsiz, {message.from_user.full_name}! Sadoon AI botiga xush kelibsiz.", reply_markup=main_keyboard)

@dp.message(F.text == "💎 Balans")
async def check_balance(message: Message):
    balance = db.get_balance(message.from_user.id)
    await message.answer(f"Sizning balansingiz: {balance} somoniy.\nID: `{message.from_user.id}`", parse_mode="Markdown")

@dp.message(F.text == "🚀 CGI Product Artist (Premium v2)")
async def cgi_start(message: Message):
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
            if "429" not in str(e):
                await message.answer(f"⚠️ Premium tizimda xatolik: {str(e)[:50]}")

        # 2. Smart Fallback (Flux + Vision)
        await message.answer("⏳ Premium limit kutmoqda... 'Smart Fallback' rejimi ishga tushdi.")
        try:
            vision_query = "Ushbu rasmdagi asosiy mahsulotni bitta so'z bilan inglizcha ayting (masalan: Cola, Soap, Perfume)."
            v_res = model.generate_content([vision_query, {"mime_type": "image/jpeg", "data": img_data}])
            p_name = v_res.text.strip() if v_res.text else "Product"
            
            f_prompt = f"Professional studio product photography of {p_name}, {vibe} style, {plat} aspect ratio, cinematic lighting, high resolution, 8k"
            import urllib.parse
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

def extract_url(text: str):
    import re
    urls = re.findall(r'http[s]?://[^\s]+', text)
    return urls[0].strip('.,()!?*') if urls else None

# --- BASIC OTHER HANDLERS ---
@dp.message()
async def echo(message: Message):
    if message.text in ["📥 Yuklab olish", "🔍 Shazam", "✍️ Takliflar", "💰 To'ldirish", "🎬 Klip Yaratish (V3) (🖼️ rasm + 🎵 musiqa)"]:
        await message.answer("🛠 Bu bo'lim hozircha test rejimida.")
    else:
        await message.answer("Asosiy menyu:", reply_markup=main_keyboard)

async def start_app():
    db.init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(start_app())
