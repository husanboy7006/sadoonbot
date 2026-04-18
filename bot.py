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
HF_TOKEN = os.getenv("HF_TOKEN", "") # Hugging Face Token for High Quality API

# Gemini sozlamalari
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-flash-lite-latest')
model_cgi = genai.GenerativeModel('gemini-3.1-flash-image-preview') # Nano Banana 2

# Tilmoch AI promtingiz
CGI_PROMPT = """
Siz dunyo darajasidagi AI Product Visualization Director, CGI artist va reklama creative direktorisiz.

❗ SIZNING VAZIFANGIZ:
Foydalanuvchi yuborgan mahsulot asosida HIGH-END, cinematic reklama RASM yaratish.

❗ MUHIM:
- Siz PROMPT yozmaysiz
- Siz FINAL RASM yaratasiz
- Siz dizayner kabi fikrlaysiz

🌐 TIL QOIDASI (QAT’IY):
- Har doim FAQAT O‘ZBEK TILIDA yozing
- Qisqa va tushunarli yozing

📥 INPUTLAR (MAJBURIY):
1. 📸 Mahsulot rasmi
2. 🎨 Vibe (faqat raqam bilan): 1=luxury, 2=fresh, 3=dark, 4=minimal, 5=energetic
3. 📐 Platforma (faqat raqam bilan): 1=instagram, 2=story, 3=banner, 4=poster

🚫 AGAR INPUT TO‘LIQ BO‘LMASA:
- Rasm yaratma
- Faqat yetishmayotgan qismini so‘ra
"""



# Foydalanuvchi tanlagan variant (Variant 3)

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



# Asosiy tugmalar (Menu)

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
        "🌐 **Tilmoch AI** — Aqlli tarjimon.\n\n"
        "**Nima qilmoqchimiz? Pastdan tanlang:** 👇\n"
        "🤖 @sadoon\_ai\_bot"
    )

    await message.answer(start_text, reply_markup=main_keyboard, parse_mode="Markdown")

    await state.clear()



# --- ADMIN PANEL ---

@dp.message(F.text == "/admin")

async def admin_stats_handler(message: Message):

    if message.from_user.id == ADMIN_ID:

        report = db.get_stats_report()

        admin_kb = InlineKeyboardMarkup(inline_keyboard=[

            [InlineKeyboardButton(text="📣 Hammasiga xabar yuborish", callback_data="broadcast_start")]

        ])

        await message.answer(report, reply_markup=admin_kb, parse_mode="HTML")

    else:

        await message.answer("❌ Bu buyruq faqat Admin uchun!")



# --- MULTICAST (AD) SYSTEM ---

@dp.callback_query(F.data == "broadcast_start")

async def start_broadcast(callback: CallbackQuery, state: FSMContext):

    if callback.from_user.id != ADMIN_ID:

        return await callback.answer("Ruxsat yo'q!", show_alert=True)

        

    await callback.answer()

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="broadcast_cancel")]])

    await callback.message.answer("📢 Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing (matn, rasm yoki video):", reply_markup=cancel_kb)

    await state.set_state(MixState.waiting_for_broadcast)



@dp.callback_query(F.data == "broadcast_cancel")

async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):

    await state.clear()

    await callback.answer("Bekor qilindi")

    await callback.message.edit_text("🚫 Xabar yuborish bekor qilindi.")

    await callback.message.answer("Menu:", reply_markup=main_keyboard)



@dp.message(MixState.waiting_for_broadcast)

async def handle_broadcast_dispatch(message: Message, state: FSMContext):

    await state.clear()

    users = db.get_all_users()

    count = 0

    blocked = 0

    

    status_msg = await message.answer(f"⏳ Xabar yuborilmoqda: 0/{len(users)}...")

    

    for user_id in users:

        try:

            await message.copy_to(chat_id=user_id)

            count += 1

            if count % 10 == 0: # Har 10 ta xabarda statusni yangilaymiz

                await status_msg.edit_text(f"⏳ Xabar yuborilmoqda: {count}/{len(users)}...")

            await asyncio.sleep(0.05) # Telegram limitlariga tushib qolmaslik uchun

        except TelegramForbiddenError:

            blocked += 1

        except Exception:

            pass

            

    await status_msg.edit_text(f"✅ **Yuborish yakunlandi!**\n\n👤 Qabul qildi: {count}\n🚫 Bloklagan: {blocked}\n📊 Jami: {len(users)}")



# --- FEEDBACK SYSTEM ---

@dp.callback_query(F.data == "feedback_choice")

async def feedback_btn(callback: CallbackQuery, state: FSMContext):

    await callback.answer()

    await callback.message.answer("✍️ Iltimos, o'z taklif yoki shikoyatingizni yozib qoldiring. Adminlarimiz uni albatta ko'rib chiqishadi:")

    await state.set_state(MixState.waiting_for_feedback)



@dp.message(MixState.waiting_for_feedback)

async def handle_feedback_msg(message: Message, state: FSMContext):

    await state.clear()

    # Adminga yuboramiz

    user_info = f"👤 Foydalanuvchi: {message.from_user.full_name}\n🆔 ID: `{message.from_user.id}`\n🔗 User: @{message.from_user.username or 'yoq'}"

    await bot.send_message(ADMIN_ID, f"📩 **Yangi Taklif!**\n\n{user_info}\n\n📝 Xabar: {message.text or 'fayl yuborildi'}")

    if not message.text:

         await message.copy_to(ADMIN_ID)

         

    await message.answer("✅ Rahmat! Taklifingiz qabul qilindi va adminga yetkazildi. 😊", reply_markup=main_keyboard)



# --- BOT FUNKSIYALARI ---

@dp.callback_query(F.data == "mix_choice")

async def mix_choice_btn(callback: CallbackQuery, state: FSMContext):

    await callback.answer()

    await callback.message.answer("📸 Juda yaxshi! Unda birinchi **rasm** yuboring:")

    await state.set_state(MixState.waiting_for_photo)



@dp.callback_query(F.data == "down_choice")

async def down_choice_btn(callback: CallbackQuery, state: FSMContext):

    await callback.answer()

    await callback.message.answer("🔗 Menga Instagram video havola (link) yuboring:")

    await state.set_state(MixState.waiting_for_downloader)



@dp.callback_query(F.data == "shazam_choice")

async def shazam_choice_btn(callback: CallbackQuery, state: FSMContext):

    await callback.answer()

    await callback.message.answer("🔍 Audio/video fayl yoki Instagram linkini yuboring:")

    await state.set_state(MixState.waiting_for_shazam)



@dp.message(MixState.waiting_for_photo, F.photo)

async def handle_photo(message: Message, state: FSMContext):

    photo_id = message.photo[-1].file_id

    await state.update_data(photo_id=photo_id)

    await message.answer("✅ Rasm tayyor!\n\n🔗 Endi audiosi bor video linkini yuboring:")

    await state.set_state(MixState.waiting_for_link)



def extract_url(text: str):

    import re

    # Matn ichidan linkni qidirish

    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)

    if not urls: return None

    # Faqat bizga kerakli platforma linkini olamiz

    for u in urls:

        # Linkni oxiridagi ortiqcha belgilardan tozalash (emoji yoki matn yopishgan bo'lsa)

        u = u.split(' ')[0].split('\n')[0].strip('.,()!?*')

        if any(x in u.lower() for x in ["tiktok.com", "instagram.com", "reels", "youtube.com", "youtu.be"]):

            print(f"DEBUG: Cleaned URL -> {u}")

            return u

    return urls[0].split(' ')[0].split('\n')[0].strip('.,()!?*')



@dp.message(MixState.waiting_for_link, F.text)

async def handle_mix_link(message: Message, state: FSMContext):

    url = extract_url(message.text)

    if not url:

        return await message.answer("❌ Havola topilmadi.")

    

    print(f"DEBUG: Extracted URL for mix: {url}")

    data = await state.get_data()

    photo_id = data.get("photo_id")

    await state.clear()

    wait_msg = await message.answer(f"⏳ Tayyorlanmoqda...\n🔗 URL: {url[:30]}...")

    

    try:

        os.makedirs("temp", exist_ok=True)

        photo_path = f"temp/{message.from_user.id}_p.jpg"

        audio_path = f"temp/{message.from_user.id}_a.mp3"

        output_path = f"temp/{message.from_user.id}_out.mp4"
        
        await bot.download(photo_id, destination=photo_path)
        success = await download_audio(url, audio_path)
        
        if success and os.path.exists(audio_path):
            await mix_image_audio(photo_path, audio_path, output_path)
            
            # Fayl hajmini tekshirish (Telegram bot uchun limit 50MB)
            file_size = os.path.getsize(output_path) / (1024 * 1024)
            if file_size > 49:
                await message.answer("⏳ Video hajmi katta, siqilmoqda...")
                compressed_path = output_path.replace(".mp4", "_compressed.mp4")
                if await compress_video(output_path, compressed_path):
                    output_path = compressed_path
            
            db.log_stats(message.from_user.id, "mix")
            await message.answer_video(video=FSInputFile(output_path), caption=FINAL_CAPTION)
        else:
            await message.answer("❌ Musiqa yuklab bo'lmadi. Havola noto'g'ri yoki videoni yuklab olishimiz cheklangan.")
        
        for f in [photo_path, audio_path, output_path]:
            if os.path.exists(f): os.remove(f)
    except Exception as e:
        await message.answer(f"❌ Xatolik: {str(e)}")
    
    await wait_msg.delete()
    await message.answer("Menu:", reply_markup=main_keyboard)

@dp.message(MixState.waiting_for_downloader, F.text)
async def handle_download_direct(message: Message, state: FSMContext):
    url = extract_url(message.text)
    if not url:
        return await message.answer("❌ Havola topilmadi.")
    
    print(f"DEBUG: Extracted URL for download: {url}")
    await state.clear()
    wait_msg = await message.answer(f"📥 Yuklanmoqda...\n🔗 URL: {url[:30]}...")
    try:
        os.makedirs("temp", exist_ok=True)
        video_path = f"temp/{message.from_user.id}_d.mp4"
        success = await download_video(url, video_path)
        db.log_stats(message.from_user.id, "download")
        
        if success and os.path.exists(video_path):
            # Fayl hajmini tekshirish
            file_size = os.path.getsize(video_path) / (1024 * 1024)
            if file_size > 49:
                await message.answer("⏳ Video hajmi 50MB dan katta, yuborish uchun siqilmoqda...")
                compressed_path = video_path.replace(".mp4", "_compressed.mp4")
                if await compress_video(video_path, compressed_path):
                    video_path = compressed_path
            
            await message.answer_video(video=FSInputFile(video_path), caption=FINAL_CAPTION)
            if os.path.exists(video_path): os.remove(video_path)
            if "_compressed" in video_path and os.path.exists(video_path.replace("_compressed", "")):
                os.remove(video_path.replace("_compressed", ""))
        else:
            await message.answer("❌ Videoni yuklab bo'lmadi. Instagram/TikTok bloklagan yoki havola noto'g'ri bo'lishi mumkin.")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {str(e)}")
    
    await wait_msg.delete()
    await message.answer("Menu:", reply_markup=main_keyboard)



@dp.message(MixState.waiting_for_shazam)

async def handle_shazam_direct(message: Message, state: FSMContext):

    await state.clear()

    wait_msg = await message.answer("🔍 Tahlil qilinmoqda...")

    try:

        os.makedirs("temp", exist_ok=True)

        temp_path = f"temp/{message.from_user.id}_s.mp3"

        if message.text:

            url = extract_url(message.text)

            if url:

                await download_audio(url, temp_path)

            else:

                return await message.answer("❌ Havola topilmadi.")

        elif message.audio or message.voice or message.video:

            file_id = message.audio.file_id if message.audio else (message.voice.file_id if message.voice else message.video.file_id)

            await bot.download(file_id, destination=temp_path)

        track = await identify_music(temp_path)

        db.log_stats(message.from_user.id, "shazam")

        if track:
            shazam_text = (
                f"🎵 **{track['title']}**\n👤 {track['subtitle']}\n\n"
                f"🔗 [Shazam orqali ochish]({track['shazam_url']})\n\n"
                f"⏳ Musiqa fayli qidirilmoqda..."
            )
            shz_msg = await message.answer(shazam_text)
            
            # Musiqani o'zini qidirib yuklaymiz
            mp3_path = f"temp/{message.from_user.id}_track.mp3"
            success = await search_and_download_music(f"{track['title']} {track['subtitle']}", mp3_path)
            
            if success and os.path.exists(mp3_path):
                await message.answer_audio(
                    audio=FSInputFile(mp3_path),
                    title=track['title'],
                    performer=track['subtitle'],
                    caption=f"🎵 {track['title']}\n🤖 @sadoon\_ai\_bot"
                )
                os.remove(mp3_path)
                # Success - update message to remove "searching..."
                final_text = (
                    f"🎵 **{track['title']}**\n👤 {track['subtitle']}\n\n"
                    f"🔗 [Shazam orqali ochish]({track['shazam_url']})\n\n"
                    f"✅ Musiqa yuborildi!"
                )
                await shz_msg.edit_text(final_text)
            else:
                await shz_msg.edit_text(f"🎵 **{track['title']}**\n👤 {track['subtitle']}\n\n❌ Afsuski, musiqa faylini topib bo'lmadi.")
        else:
            await message.answer("❌ Musiqani aniqlab bo'lmadi.")

        if os.path.exists(temp_path): os.remove(temp_path)

    except Exception as e:

        await message.answer(f"❌ Xatolik: {str(e)}")

    await wait_msg.delete()
    await message.answer("Menu:", reply_markup=main_keyboard)

@dp.callback_query(F.data == "gemini_choice")
async def gemini_choice_btn(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "🌐 **Tilmoch AI rejimiga o'tdingiz.**\n\n"
        "Matn yozing yoki audio xabar yuboring, men uni Uzb-Rus-Chn tillarida professional tarjima qilib beraman:"
    )
    await state.set_state(MixState.waiting_for_gemini)

@dp.message(MixState.waiting_for_gemini, F.content_type.in_({'text', 'voice', 'audio'}))
async def handle_gemini_chat(message: Message, state: FSMContext):
    if message.text and message.text.lower() in ["menu", "/start", "back"]:
        await state.clear()
        return await message.answer("Bosh menyu:", reply_markup=main_keyboard)

    wait_msg = await message.answer("⏳ Tilmoch AI tahlil qilmoqda...")
    
    try:
        content = []
        # Tizimli ko'rsatmani qo'shamiz
        GEMINI_SYSTEM_PROMPT = """
Sizning ismingiz: Tilmoch AI
Rolingiz: O‘zbek, Rus va Xitoy tillari o‘rtasida professional darajadagi tezkor tarjima va audio tahlilni amalga oshirish.

QOIDALAR:
1. Hech qachon o‘zingizni tanishtirmang va kirish gaplari yozmang.
2. Foydalanuvchi nima yuborsa ham darhol tarjimaga o‘ting, ortiqcha gap yozmang.
3. Faqat tarjima bilan shug‘ullaning. Agar foydalanuvchi boshqa narsa so‘rasa: "Faqat tarjima bilan shug‘ullanaman." deb javob bering.

QAYTA ISHLASH:
- O‘zbekcha yozilsa: Rus va Xitoy tillariga tarjima qiling.
- Ruscha yozilsa: O‘zbek tiliga tarjima qiling.
- Xitoycha yozilsa: O‘zbek tiliga tarjima qiling.
"""
        content.append(GEMINI_SYSTEM_PROMPT)
        
        if message.text:
            content.append(f"Foydalanuvchi matni: {message.text}")
        elif message.voice or message.audio:
            file_id = message.voice.file_id if message.voice else message.audio.file_id
            file = await bot.get_file(file_id)
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as resp:
                    if resp.status == 200:
                        audio_data = await resp.read()
                        content.append({"mime_type": "audio/ogg" if message.voice else "audio/mpeg", "data": audio_data})
                    else:
                        return await message.answer("❌ Audioni yuklab olishda xatolik yuz berdi.", parse_mode=None)
        
        response = model.generate_content(content)
        
        if response.text:
            await message.answer(response.text, parse_mode=None)
        else:
            await message.answer("❌ Gemini javob bera olmadi.", parse_mode=None)
            
    except Exception as e:
        await message.answer(f"❌ Tilmoch AI xatoligi: {str(e)}", parse_mode=None)
    
    await wait_msg.delete()

# --- PREMIUM CGI & PAYMENT HANDLERS ---

@dp.callback_query(F.data == "balance_info")
async def balance_info_handler(callback: CallbackQuery):
    balance = db.get_user_balance(callback.from_user.id)
    await callback.answer()
    await callback.message.answer(f"👤 **Sizning balansingiz:** {balance} kredit\n\n"
                                f"🚀 *CGI Product Artist* xizmati uchun har bir urinish 1 kredit sarflaydi.")

@dp.callback_query(F.data == "fill_balance")
async def fill_balance_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    text = (
        f"💰 **Hisobni to'ldirish**\n\n"
        f"1 ta kredit narxi: {PRICE_PER_CGI}\n"
        f"Quyidagi kartaga to'lovni amalga oshiring:\n\n"
        f"`{CARD_DATA}`\n\n"
        f"To'lovdan so'ng chekni (skrinshotni) shu botga yuboring. Admin tasdiqlagach, kredit hisobingizga qo'shiladi."
    )
    await callback.message.answer(text, parse_mode="Markdown")
    await state.set_state(MixState.waiting_for_payment_proof)

@dp.message(MixState.waiting_for_payment_proof, F.photo)
async def handle_payment_proof(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Rahmat! Chekingiz adminga yuborildi. Tasdiqlashni kuting.")
    
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash (+1)", callback_data=f"confirm_pay_{message.from_user.id}_1")],
        [InlineKeyboardButton(text="✅ Tasdiqlash (+5)", callback_data=f"confirm_pay_{message.from_user.id}_5")],
        [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_pay_{message.from_user.id}")]
    ])
    
    user_info = f"👤 Mijoz: {message.from_user.full_name}\n🆔 ID: `{message.from_user.id}`"
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"💰 **Yangi to'lov cheki!**\n\n{user_info}", reply_markup=admin_kb)

@dp.callback_query(F.data.startswith("confirm_pay_"))
async def confirm_payment_callback(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    _, _, user_id, amount = callback.data.split("_")
    user_id = int(user_id)
    amount = int(amount)
    
    if db.update_balance(user_id, amount):
        await callback.message.edit_caption(caption=callback.message.caption + f"\n\n✅ **TASDIQLANDI!** (+{amount} kredit)")
        await bot.send_message(user_id, f"🎉 **Xushxabar!** To'lovingiz tasdiqlandi. Hisobingizga {amount} ta kredit qo'shildi.")
    else:
        await callback.answer("Xatolik yuz berdi")

@dp.callback_query(F.data.startswith("reject_pay_"))
async def reject_payment_callback(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    user_id = int(callback.data.split("_")[2])
    await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ **RAD ETILDI!**")
    await bot.send_message(user_id, "❌ Uzr, to'lovingiz rad etildi. Iltimos, ma'lumotlarni tekshirib qaytadan urinib ko'ring yoki adminga murojaat qiling.")

@dp.callback_query(F.data == "cgi_choice")
async def cgi_choice_handler(callback: CallbackQuery, state: FSMContext):
    # Admin uchun balans cheksiz
    if callback.from_user.id != ADMIN_ID:
        balance = db.get_user_balance(callback.from_user.id)
        if balance < 1:
            await callback.answer("Balansingiz yetarli emas!", show_alert=True)
            return await fill_balance_handler(callback, state)
        
    await callback.answer()
    await callback.message.answer("🚀 **Premium CGI Product Artist** rejimiga xush kelibsiz!\n\n📸 Birinchi navbatda mahsulot rasmini yuboring:")
    await state.set_state(MixState.waiting_for_cgi_photo)

@dp.message(MixState.waiting_for_cgi_photo, F.photo)
async def handle_cgi_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(cgi_photo=photo_id)
    
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
    photo_id = data.get("cgi_photo")
    choices = message.text.split()
    
    if len(choices) < 2:
        return await message.answer("Iltimos, vibe va platformani tanlang (masalan: `1 2`)")

    vibe_map = {"1": "Luxury", "2": "Fresh", "3": "Dark", "4": "Minimal", "5": "Energetic"}
    plat_map = {"1": "Instagram (4:5)", "2": "Story (9:16)", "3": "Banner (16:9)", "4": "Poster"}
    
    vibe = vibe_map.get(choices[0], "Luxury")
    plat = plat_map.get(choices[1], "Instagram")
    
    await state.clear()
    wait_msg = await message.answer("⏳ **CGI Artist ishlamoqda...**\nBu biroz vaqt olishi mumkin.")
    
    try:
        # Multimodal Gemini call
        file = await bot.get_file(photo_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                image_data = await resp.read()
        
        prompt_with_choices = f"{CGI_PROMPT}\n\nFOYDALANUVCHI TANLOVI:\nVibe: {vibe}\nPlatforma: {plat}"
        
        content = [
            prompt_with_choices,
            {"mime_type": "image/jpeg", "data": image_data}
        ]
        
        # 1. Gemini orqali dizayn va inglizcha promt yaratamiz
        # Promptga rasm yaratish uchun aniq ko'rsatma beramiz
        reasoning_prompt = f"{CGI_PROMPT}\n\nFOYDALANUVCHI TANLOVI:\nVibe: {vibe}\nPlatforma: {plat}\n\nVAZIFA: Faqat va faqat ingliz tilida rasm yaratish uchun juda batafsil 'image generation prompt' qaytaring. Ortiqcha gap yozmang."
        
        response = model.generate_content([reasoning_prompt, {"mime_type": "image/jpeg", "data": image_data}])
        
        # --- 1-URINISH: NANO BANANA 2 (Eng yuqori sifat) ---
        try:
            nano_prompt = f"{CGI_PROMPT}\n\nVAZIFA: Ushbu mahsulotni o'zini va detallarini mutlaqo o'zgartirmasdan, professional reklama rasmini yaratib ber.\nVibe: {vibe}\nPlatforma: {plat}"
            
            response = await asyncio.wait_for(
                model_cgi.generate_content_async([nano_prompt, {"mime_type": "image/jpeg", "data": image_data}]),
                timeout=100
            )
            
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        from aiogram.types import BufferedInputFile
                        image_file = BufferedInputFile(part.inline_data.data, filename="cgi_result.jpg")
                        await message.answer_photo(photo=image_file, caption=f"💎 **Nano Banana Art** (Studio Quality)")
                        if message.from_user.id != ADMIN_ID: db.update_balance(message.from_user.id, -1)
                        db.log_stats(message.from_user.id, "cgi")
                        try: await wait_msg.delete()
                        except: pass
                        await message.answer("Menyu:", reply_markup=main_keyboard)
                        return
        except Exception as ne:
            print(f"Nano Error: {ne}")

        # --- 2-URINISH: FLUX (Zaxira) ---
        try:
            await message.answer("⏳ Premium server band, zaxira tizimi ishlamoqda...")
            reasoning = f"{CGI_PROMPT}\n\nVAZIFA: Inglizcha rasm promtini yozing. Vibe: {vibe}"
            resp = model.generate_content([reasoning, {"mime_type": "image/jpeg", "data": image_data}])
            
            if resp.text:
                import urllib.parse
                clean_p = resp.text.replace('"', '').replace('\n', ' ').strip()[:200]
                safe_p = urllib.parse.quote(clean_p)
                image_url = f"https://image.pollinations.ai/prompt/{safe_p}?width=800&height=800&nologo=true&model=flux"
                
                temp_path = f"temp/{message.from_user.id}_f.jpg"
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url, timeout=60) as r:
                         if r.status == 200:
                             with open(temp_path, "wb") as f: f.write(await r.read())
                             from aiogram.types import FSInputFile
                             await message.answer_photo(photo=FSInputFile(temp_path), caption="🚀 CGI Result (Backup)")
                             if os.path.exists(temp_path): os.remove(temp_path)
                             if message.from_user.id != ADMIN_ID: db.update_balance(message.from_user.id, -1)
                             db.log_stats(message.from_user.id, "cgi")
                         else:
                             await message.answer("❌ Serverda vaqtinchalik xatolik. Birozdan so'ng urinib ko'ring.")
        except Exception as e:
            print(f"Global CGI Error: {e}")
            await message.answer(f"❌ Xatolik yuz berdi: {str(e)[:100]}")
    
    try:
        await wait_msg.delete()
    except: pass
    await message.answer("Menyu:", reply_markup=main_keyboard)

async def main():
    db.init_db()
    
    # Debug: Mavjud modellarni tekshirish
    try:
        available_models = [m.name for m in genai.list_models()]
        print(f"[*] Available Gemini models: {available_models}")
    except Exception as e:
        print(f"[!] Could not list models: {e}")

    commands = [

        BotCommand(command="start", description="🚀 Botni boshlash"),

        BotCommand(command="admin", description="📊 Statistika (Admin)")

    ]

    for i in range(15):


        try:


            await bot.set_my_commands(commands)


            print("Bot muvaffaqiyatli ishga tushdi...")


            await bot.delete_webhook(drop_pending_updates=True)


            await dp.start_polling(bot)


            break


        except Exception as e:


            print(f"Tarmoq kutilmoqda ({i+1}): {e}")


            import asyncio


            await asyncio.sleep(4)



if __name__ == "__main__":

    asyncio.run(main())

