import os
import sys
import json
import ssl
import socket
import asyncio
import urllib.request
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties

import database as db
import google.generativeai as genai
from mixer import download_audio, mix_image_audio, identify_music, download_video, search_and_download_music, compress_video

# --- [UNIVERSAL DNS PATCH] ---
ctx = ssl._create_unverified_context()
old_getaddrinfo = socket.getaddrinfo
dns_cache = {}

def new_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host in ["127.0.0.1", "localhost", "0.0.0.0", "api.telegram.org"]:
        if host == "api.telegram.org":
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('149.154.167.220', port))]
        return old_getaddrinfo(host, port, family, type, proto, flags)
    
    if host in dns_cache:
        ip = dns_cache[host]
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (ip, port))]
    
    try:
        url = f"https://1.1.1.1/dns-query?name={host}&type=A"
        req = urllib.request.Request(url, headers={'accept': 'application/dns-json'})
        with urllib.request.urlopen(req, timeout=5, context=ctx) as response:
            data = json.loads(response.read().decode())
            if "Answer" in data:
                for ans in data["Answer"]:
                    if ans["type"] == 1:
                        ip = ans["data"]
                        dns_cache[host] = ip
                        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (ip, port))]
    except:
        pass
    return old_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = new_getaddrinfo

# Windows terminal UTF-8 support
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# SETTINGS
TOKEN = "8727075082:AAEQrVaA_S-D6wHy1URANE2NgLVMs5d7yXw"
GEMINI_KEY = os.getenv("GEMINI_KEY", "AIzaSyDl4kbccq-GUe9BP8Kwc-YTBDcXhszp5rw")
HF_TOKEN = os.getenv("HF_TOKEN", "")

# Gemini sozlamalari
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-flash-lite-latest')
model_cgi = genai.GenerativeModel('gemini-3.1-flash-image-preview')

CGI_PROMPT = """
Siz dunyo darajasidagi AI Product Visualization Director, CGI artist va reklama creative direktorisiz.
Vazifa: Foydalanuvchi mahsuloti uchun HD darajadagi reklama dizaynini yaratish.
Til: O'zbek tili.
"""

FINAL_CAPTION = (
    "✅ **Bajarildi!**\n\n"
    "🎵 Klip yaratuvchi: Sadoon AI Bot\n"
    "🔗 @sadoon_ai_bot\n\n"
    "Do'stlaringizga ham ulashing! 📲"
)

session = AiohttpSession(timeout=60)
bot = Bot(token=TOKEN, session=session, default=DefaultBotProperties(parse_mode='Markdown'))
dp = Dispatcher()

class MixState(StatesGroup):
    waiting_for_photo = State()
    waiting_for_link = State()
    waiting_for_downloader = State()
    waiting_for_shazam = State()
    waiting_for_feedback = State()
    waiting_for_broadcast = State()
    waiting_for_gemini = State()
    waiting_for_cgi_photo = State()
    waiting_for_cgi_choices = State()
    waiting_for_payment_proof = State()

# Menyu
main_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🎬 Klip Yaratish (V3) (🖼 rasm + 🎵 musiqa)", callback_data="mix_choice")],
    [InlineKeyboardButton(text="🚀 CGI Product Artist (Premium v2)", callback_data="cgi_choice")],
    [
        InlineKeyboardButton(text="📥 Yuklab olish", callback_data="down_choice"),
        InlineKeyboardButton(text="🔍 Shazam", callback_data="shazam_choice")
    ],
    [
        InlineKeyboardButton(text="🌐 Tilmoch AI", callback_data="gemini_choice"),
        InlineKeyboardButton(text="👤 Balans", callback_data="balance_info")
    ],
    [
        InlineKeyboardButton(text="✍️ Takliflar", callback_data="feedback_choice"),
        InlineKeyboardButton(text="💰 To'ldirish", callback_data="fill_balance")
    ]
])

CARD_DATA = "💳 5614 6820 2858 4441"
PRICE_PER_CGI = "2 000 UZS"
ADMIN_ID = 7110271171 

@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
    db.add_user(message.from_user.id, message.from_user.username)
    start_text = (
        "👑 **Sadoon AI Premium Bot-ga xush kelibsiz!**\n\n"
        "Men sizga eng yuqori sifatli (CGI, KLIP, TARJIMA) xizmatlarni taqdim etaman.\n\n"
        "🎬 **Klip yaratish** — Rasm va musiqani birlashtirish.\n"
        "📥 **Yuklab olish** — Instagram va TikTok mediya yuklagich.\n"
        "🔍 **Shazam** — Musiqalarni aniqlash.\n"
        "🌐 **Tilmoch AI** — Aqlli tarjimon."
    )
    await message.answer(start_text, reply_markup=main_keyboard)
    await state.clear()

# --- ADMIN PANEL ---
@dp.message(F.text == "/admin")
async def admin_stats_handler(message: Message):
    if message.from_user.id == ADMIN_ID:
        report = db.get_stats_report()
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📣 Xabar yuborish", callback_data="broadcast_start")]])
        await message.answer(report, reply_markup=admin_kb, parse_mode="HTML")
    else:
        await message.answer("❌ Faqat admin uchun!")

@dp.callback_query(F.data == "broadcast_start")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    await callback.answer()
    await callback.message.answer("📢 Xabarni yozing:")
    await state.set_state(MixState.waiting_for_broadcast)

@dp.message(MixState.waiting_for_broadcast)
async def handle_broadcast_dispatch(message: Message, state: FSMContext):
    await state.clear()
    users = db.get_all_users()
    count = 0
    for user_id in users:
        try:
            await message.copy_to(chat_id=user_id)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Yuborildi: {count}")

# --- FEEDBACK ---
@dp.callback_query(F.data == "feedback_choice")
async def feedback_btn(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("✍️ Taklifingizni yozing:")
    await state.set_state(MixState.waiting_for_feedback)

@dp.message(MixState.waiting_for_feedback)
async def handle_feedback_msg(message: Message, state: FSMContext):
    await state.clear()
    await bot.send_message(ADMIN_ID, f"📩 Taklif: {message.text}\n👤 {message.from_user.full_name}")
    await message.answer("✅ Rahmat!", reply_markup=main_keyboard)

# --- KLIP YARATISH ---
@dp.callback_query(F.data == "mix_choice")
async def mix_choice_btn(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("📸 Rasm yuboring:")
    await state.set_state(MixState.waiting_for_photo)

@dp.message(MixState.waiting_for_photo, F.photo)
async def handle_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await message.answer("✅ Endi video havola (link) yuboring:")
    await state.set_state(MixState.waiting_for_link)

@dp.message(MixState.waiting_for_link, F.text)
async def handle_mix_link(message: Message, state: FSMContext):
    from bot import extract_url
    url = extract_url(message.text)
    if not url: return await message.answer("❌ Havola xato.")
    data = await state.get_data()
    photo_id = data.get("photo_id")
    await state.clear()
    wait_msg = await message.answer("⏳ Ishlanmoqda...")
    try:
        os.makedirs("temp", exist_ok=True)
        photo_path = f"temp/{message.from_user.id}_p.jpg"
        audio_path = f"temp/{message.from_user.id}_a.mp3"
        output_path = f"temp/{message.from_user.id}_out.mp4"
        await bot.download(photo_id, destination=photo_path)
        if await download_audio(url, audio_path):
            await mix_image_audio(photo_path, audio_path, output_path)
            await message.answer_video(video=FSInputFile(output_path), caption=FINAL_CAPTION)
            db.log_stats(message.from_user.id, "mix")
        else: await message.answer("❌ Musiqa xatosi.")
        for f in [photo_path, audio_path, output_path]:
            if os.path.exists(f): os.remove(f)
    except Exception as e: await message.answer(f"❌ Xato: {e}")
    await wait_msg.delete()
    await message.answer("Menyu:", reply_markup=main_keyboard)

# --- YUKLAB OLISH ---
@dp.callback_query(F.data == "down_choice")
async def down_choice_btn(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("🔗 Video havolasini yuboring:")
    await state.set_state(MixState.waiting_for_downloader)

@dp.message(MixState.waiting_for_downloader, F.text)
async def handle_download_direct(message: Message, state: FSMContext):
    from bot import extract_url
    url = extract_url(message.text)
    if not url: return await message.answer("❌ Havola topilmadi.")
    await state.clear()
    wait_msg = await message.answer("📥 Yuklanmoqda...")
    try:
        video_path = f"temp/{message.from_user.id}_d.mp4"
        if await download_video(url, video_path):
            await message.answer_video(video=FSInputFile(video_path), caption=FINAL_CAPTION)
            db.log_stats(message.from_user.id, "download")
            if os.path.exists(video_path): os.remove(video_path)
        else: await message.answer("❌ Yuklab bo'lmadi.")
    except Exception as e: await message.answer(f"❌ Xato: {e}")
    await wait_msg.delete()
    await message.answer("Menyu:", reply_markup=main_keyboard)

# --- SHAZAM ---
@dp.callback_query(F.data == "shazam_choice")
async def shazam_choice_btn(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("🔍 Audio yoki Instagram link yuboring:")
    await state.set_state(MixState.waiting_for_shazam)

@dp.message(MixState.waiting_for_shazam)
async def handle_shazam_direct(message: Message, state: FSMContext):
    await state.clear()
    wait_msg = await message.answer("🔍 Qidirilmoqda...")
    try:
        temp_path = f"temp/{message.from_user.id}_s.mp3"
        from bot import extract_url
        if message.text:
            url = extract_url(message.text)
            if url: await download_audio(url, temp_path)
        elif message.audio or message.voice or message.video:
            fid = message.audio.file_id if message.audio else (message.voice.file_id if message.voice else message.video.file_id)
            await bot.download(fid, destination=temp_path)
        
        track = await identify_music(temp_path)
        if track:
            await message.answer(f"🎵 {track['title']}\n👤 {track['subtitle']}")
            db.log_stats(message.from_user.id, "shazam")
        else: await message.answer("❌ Topilmadi.")
        if os.path.exists(temp_path): os.remove(temp_path)
    except Exception as e: await message.answer(f"❌ Xato: {e}")
    await wait_msg.delete()
    await message.answer("Menyu:", reply_markup=main_keyboard)

# --- TILMOCH AI ---
@dp.callback_query(F.data == "gemini_choice")
async def gemini_choice_btn(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("🌐 Tilmoch AI-ga matn yoki audio yuboring:")
    await state.set_state(MixState.waiting_for_gemini)

@dp.message(MixState.waiting_for_gemini)
async def handle_gemini_chat(message: Message, state: FSMContext):
    if message.text and message.text.lower() in ["menu", "/start"]:
        await state.clear()
        return await message.answer("Menyu:", reply_markup=main_keyboard)
    wait_msg = await message.answer("⏳...")
    try:
        res = model.generate_content(message.text)
        await message.answer(res.text)
    except: await message.answer("❌ Xatolik.")
    await wait_msg.delete()

# --- BALANS VA TO'LOV ---
@dp.callback_query(F.data == "balance_info")
async def balance_info_handler(callback: CallbackQuery):
    bal = db.get_user_balance(callback.from_user.id)
    await callback.answer()
    await callback.message.answer(f"👤 Balansingiz: {bal} kredit")

@dp.callback_query(F.data == "fill_balance")
async def fill_balance_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(f"💰 To'lov: `{CARD_DATA}`\nChekni yuboring.")
    await state.set_state(MixState.waiting_for_payment_proof)

@dp.message(MixState.waiting_for_payment_proof, F.photo)
async def handle_payment_proof(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Adminga yuborildi.")
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ +1", callback_data=f"confirm_pay_{message.from_user.id}_1")]])
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption="💰 Chek!", reply_markup=admin_kb)

@dp.callback_query(F.data.startswith("confirm_pay_"))
async def confirm_payment_callback(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    _, _, uid, amt = callback.data.split("_")
    if db.update_balance(int(uid), int(amt)):
        await bot.send_message(int(uid), "✅ Tasdiqlandi!")
        await callback.message.edit_caption(caption="✅")

# --- CGI PRODUCT ARTIST (FAIL-PROOF) ---
@dp.callback_query(F.data == "cgi_choice")
async def cgi_choice_handler(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        if db.get_user_balance(callback.from_user.id) < 1:
            return await fill_balance_handler(callback, state)
    await callback.answer()
    await callback.message.answer("🚀 Premium CGI: Mahsulot rasmini yuboring:")
    await state.set_state(MixState.waiting_for_cgi_photo)

@dp.message(MixState.waiting_for_cgi_photo, F.photo)
async def handle_cgi_photo(message: Message, state: FSMContext):
    await state.update_data(cgi_photo=message.photo[-1].file_id)
    await message.answer("🎨 Vibe: 1-5, Platforma: 1-4. Misol: `1 2`")
    await state.set_state(MixState.waiting_for_cgi_choices)

@dp.message(MixState.waiting_for_cgi_choices, F.text)
async def handle_cgi_final(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        choices = message.text.split()
        if len(choices) < 2: return await message.answer("Misol: `1 2`")
        
        vibe_map = {"1":"Luxury", "2":"Fresh", "3":"Dark", "4":"Minimal", "5":"Energetic"}
        plat_map = {"1":"Instagram", "2":"Story", "3":"Banner", "4":"Poster"}
        vibe, plat = vibe_map.get(choices[0], "Luxury"), plat_map.get(choices[1], "Instagram")
        
        await state.clear()
        wait_msg = await message.answer("⏳ CGI ishlanmoqda...")
        
        file = await bot.get_file(data.get("cgi_photo"))
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as r: img_data = await r.read()

        # Try Gemini Nano
        try:
            res = await asyncio.wait_for(model_cgi.generate_content_async([CGI_PROMPT, {"mime_type":"image/jpeg","data":img_data}]), timeout=80)
            if res.candidates and res.candidates[0].content.parts:
                for part in res.candidates[0].content.parts:
                    if hasattr(part, 'inline_data'):
                        from aiogram.types import BufferedInputFile
                        await message.answer_photo(photo=BufferedInputFile(part.inline_data.data, filename="cgi.jpg"), caption="💎 Premium Result")
                        return await finish_cgi(message, wait_msg)
        except Exception as ne: print(f"Nano failed: {ne}")

        # Emergency Fallback to Flux
        await message.answer("⏳ Tezkor serverga ulanilmoqda...")
        prompt = f"Professional advertising of product, {vibe} style, {plat} format, high resolution"
        import urllib.parse
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=800&height=800&nologo=true"
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                if r.status == 200:
                    from aiogram.types import BufferedInputFile
                    await message.answer_photo(photo=BufferedInputFile(await r.read(), filename="cgi_f.jpg"), caption="🚀 Fast Result")
                    return await finish_cgi(message, wait_msg)
                else: await message.answer("❌ Server xatosi.")
    except Exception as e: await message.answer(f"❌ Xatolik: {e}")
    await wait_msg.delete()
    await message.answer("Menyu:", reply_markup=main_keyboard)

async def finish_cgi(message, wait_msg):
    if message.from_user.id != ADMIN_ID: db.update_balance(message.from_user.id, -1)
    db.log_stats(message.from_user.id, "cgi")
    try: await wait_msg.delete()
    except: pass
    await message.answer("Menyu:", reply_markup=main_keyboard)

def extract_url(text: str):
    import re
    urls = re.findall(r'http[s]?://[^\s]+', text)
    return urls[0].strip('.,()!?*') if urls else None

async def main():
    db.init_db()
    try: await bot.set_my_commands([BotCommand(command="start", description="🚀")])
    except: pass
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
