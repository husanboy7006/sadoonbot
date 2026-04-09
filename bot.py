import socket
import urllib.request
import json
import ssl

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
    except Exception as e:
        pass
    
    return old_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = new_getaddrinfo

import socket

# Telegram DNS DNS-resolution xatosini chetlab o'tish uchun monkey-patch
import asyncio

import os

import aiohttp

import sys



# Windows terminalda Unicode (emoji) xatolarni oldini olish uchun

if sys.stdout.encoding != 'utf-8':

    try:

        sys.stdout.reconfigure(encoding='utf-8')

    except AttributeError:

        pass # Eski python versiyalari uchun

from aiogram import Bot, Dispatcher, F, types

from aiogram.filters import CommandStart

from aiogram.fsm.context import FSMContext

from aiogram.fsm.state import State, StatesGroup

from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from mixer import download_audio, mix_image_audio, identify_music, download_video, search_and_download_music, compress_video

import database as db
import google.generativeai as genai



from aiogram.client.session.aiohttp import AiohttpSession

from aiogram.client.default import DefaultBotProperties



TOKEN = "8727075082:AAEQrVaA_S-D6wHy1URANE2NgLVMs5d7yXw"  # Asosiy bot

# TOKEN = "8307406554:AAHgJXXn8PcQYvdJm65aDXXkw0SUSzSQNu8"  # Test boti

API_URL = os.getenv("API_URL", "http://127.0.0.1:7860/api/mix")
GEMINI_KEY = "AIzaSyDl4kbccq-GUe9BP8Kwc-YTBDcXhszp5rw"

# Gemini sozlamalari
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-flash-latest')

# Tilmoch AI promtingiz
GEMINI_PROMPT = """
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

JAVOB FORMATI (QAT'IY SAQLANSIN):
Original: [Matn]
O‘zbekcha: [Matn]
Ruscha: ```[Matn]```
Xitoycha: ```[Matn]```
Talaffuz: [Xitoycha Pinyin ohanglari bilan + o‘zbekcha o‘qilishi]
Namuna javoblar: [2 ta mos javob varianti]
"""



# Foydalanuvchi tanlagan variant (Variant 3)

FINAL_CAPTION = (
    "✅ **Bajarildi!**\n\n"
    "🎵 Klip yaratuvchi: Sadoon AI Bot\n"
    "🔗 @sadoon\_ai\_bot\n\n"
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



# Asosiy tugmalar (Menu)

main_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🎬 Klip yasash (🖼 rasm + 🎵 musiqa)", callback_data="mix_choice")],
    [InlineKeyboardButton(text="📥 Instagram / TikTok", callback_data="down_choice")],
    [
        InlineKeyboardButton(text="🔍 Musiqani topish", callback_data="shazam_choice"),
        InlineKeyboardButton(text="🤖 Gemini AI Chat", callback_data="gemini_choice")
    ],
    [
        InlineKeyboardButton(text="✍️ Takliflar", callback_data="feedback_choice"),
        InlineKeyboardButton(text="🌐 Sadoon AI Sayti", url="https://sadoonbot.vercel.app/")
    ]
])

ADMIN_ID = 7110271171 



@dp.message(CommandStart())

async def command_start_handler(message: Message, state: FSMContext) -> None:

    db.add_user(message.from_user.id, message.from_user.username)

    start_text = (
        "👋 **Salom! Men Sadoon AI botiman.**\n\n"
        "Men sizga quyidagi ishlarda yordam bera olaman:\n"
        "🎬 **Klip yasash** — Rasmingizga sevimli musiqangizni qo'shib video tayyorlash.\n"
        "📥 **Yuklab olish** — Instagram va TikTok videolarini yuklash.\n"
        "🔍 **Shazam** — Istalgan musiqani bir zumda topish.\n\n"
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
            mix_image_audio(photo_path, audio_path, output_path)
            
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
    await callback.message.answer("🤖 **Gemini AI rejimiga o'tdingiz.**\n\nIstalgan savolingizni bering yoki tarjima qilmoqchi bo'lgan matningizni yuboring:")
    await state.set_state(MixState.waiting_for_gemini)

@dp.message(MixState.waiting_for_gemini, F.content_type.in_({'text', 'voice', 'audio'}))
async def handle_gemini_chat(message: Message, state: FSMContext):
    # "Menu" so'zi bo'lsa chiqib ketamiz
    if message.text and message.text.lower() in ["menu", "/start", "back"]:
        await state.clear()
        return await message.answer("Bosh menyu:", reply_markup=main_keyboard)

    wait_msg = await message.answer("⏳ Tilmoch AI tahlil qilmoqda...")
    
    try:
        content = []
        # Tizimli ko'rsatmani qo'shamiz
        content.append(GEMINI_PROMPT)
        
        if message.text:
            content.append(f"Foydalanuvchi matni: {message.text}")
        
        elif message.voice or message.audio:
            # Audioni yuklab olish
            file_id = message.voice.file_id if message.voice else message.audio.file_id
            file = await bot.get_file(file_id)
            
            # Faylni xotiraga (memory) yuklaymiz (Diskga yozib o'tirmaymiz)
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"
            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as resp:
                    if resp.status == 200:
                        audio_data = await resp.read()
                        content.append({
                            "mime_type": "audio/ogg" if message.voice else "audio/mpeg",
                            "data": audio_data
                        })
                    else:
                        return await message.answer("❌ Audioni yuklab olishda xatolik yuz berdi.", parse_mode=None)
        
        # Jeneratsiya qilish
        response = model.generate_content(content)
        
        # Javobni yuborish (Markdown xatosi bo'lsa oddiy matn sifatida yuboramiz)
        if response.text:
            try:
                await message.answer(response.text, parse_mode="Markdown")
            except:
                await message.answer(response.text, parse_mode=None)
        else:
            await message.answer("❌ Gemini javob bera olmadi.", parse_mode=None)
            
    except Exception as e:
        await message.answer(f"❌ Tilmoch AI xatoligi: {str(e)}", parse_mode=None)
    
    await wait_msg.delete()



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

