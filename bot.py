import socket

# Telegram DNS DNS-resolution xatosini chetlab o'tish uchun monkey-patch
old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host == 'api.telegram.org':
        # Telegram API serverining aniq IP manzili
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('149.154.167.220', port))]
    return old_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = new_getaddrinfo

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

from mixer import download_audio, mix_image_audio, identify_music, download_video

import database as db



from aiogram.client.session.aiohttp import AiohttpSession

from aiogram.client.default import DefaultBotProperties



TOKEN = "8727075082:AAEQrVaA_S-D6wHy1URANE2NgLVMs5d7yXw"  # Asosiy bot

# TOKEN = "8307406554:AAHgJXXn8PcQYvdJm65aDXXkw0SUSzSQNu8"  # Test boti

API_URL = os.getenv("API_URL", "http://127.0.0.1:7860/api/mix")



# Foydalanuvchi tanlagan variant (Variant 3)

FINAL_CAPTION = (

    "тЬЕ **Bajarildi!**\n\n"

    "ЁЯОе Klip yaratuvchi: Sadoon AI Bot\n"

    "ЁЯФЧ @sadoon\_ai\_bot\n\n"

    "Do'stlaringizga ham ulashing! ЁЯУд"

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



# Asosiy tugmalar (Menu)

main_keyboard = InlineKeyboardMarkup(inline_keyboard=[

    [InlineKeyboardButton(text="ЁЯОм Klip yasash (ЁЯЦ╝ rasm + ЁЯО╡ musiqa)", callback_data="mix_choice")],

    [InlineKeyboardButton(text="ЁЯУе Instagram (Video yuklash)", callback_data="down_choice")],

    [

        InlineKeyboardButton(text="ЁЯФН Musiqani topish", callback_data="shazam_choice"),

        InlineKeyboardButton(text="тЬНя╕П Takliflar", callback_data="feedback_choice")

    ],

    [InlineKeyboardButton(text="ЁЯМР Sadoon AI Sayti", url="https://sadoonbot.vercel.app/")]

])



ADMIN_ID = 7110271171 



@dp.message(CommandStart())

async def command_start_handler(message: Message, state: FSMContext) -> None:

    db.add_user(message.from_user.id, message.from_user.username)

    start_text = (

        "ЁЯСЛ **Salom! Men Sadoon AI botiman.**\n\n"

        "Men sizga quyidagi ishlarda yordam bera olaman:\n"

        "ЁЯОм **Klip yasash** тАФ Rasmingizga sevimli musiqangizni qo'shib video tayyorlash.\n"

        "ЁЯУе **Instagram** тАФ Reels va har qanday videoni yuklab olish.\n"

        "ЁЯФН **Shazam** тАФ Istalgan musiqani bir zumda topish.\n\n"

        "**Nima qilmoqchimiz? Pastdan tanlang:** ЁЯСЗ"

    )

    await message.answer(start_text, reply_markup=main_keyboard, parse_mode="Markdown")

    await state.clear()



# --- ADMIN PANEL ---

@dp.message(F.text == "/admin")

async def admin_stats_handler(message: Message):

    if message.from_user.id == ADMIN_ID:

        report = db.get_stats_report()

        admin_kb = InlineKeyboardMarkup(inline_keyboard=[

            [InlineKeyboardButton(text="ЁЯУв Hammasiga xabar yuborish", callback_data="broadcast_start")]

        ])

        await message.answer(report, reply_markup=admin_kb, parse_mode="HTML")

    else:

        await message.answer("тЭМ Bu buyruq faqat Admin uchun!")



# --- MULTICAST (AD) SYSTEM ---

@dp.callback_query(F.data == "broadcast_start")

async def start_broadcast(callback: CallbackQuery, state: FSMContext):

    if callback.from_user.id != ADMIN_ID:

        return await callback.answer("Ruxsat yo'q!", show_alert=True)

        

    await callback.answer()

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="тЭМ Bekor qilish", callback_data="broadcast_cancel")]])

    await callback.message.answer("ЁЯУг Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing (matn, rasm yoki video):", reply_markup=cancel_kb)

    await state.set_state(MixState.waiting_for_broadcast)



@dp.callback_query(F.data == "broadcast_cancel")

async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):

    await state.clear()

    await callback.answer("Bekor qilindi")

    await callback.message.edit_text("ЁЯЪл Xabar yuborish bekor qilindi.")

    await callback.message.answer("Menu:", reply_markup=main_keyboard)



@dp.message(MixState.waiting_for_broadcast)

async def handle_broadcast_dispatch(message: Message, state: FSMContext):

    await state.clear()

    users = db.get_all_users()

    count = 0

    blocked = 0

    

    status_msg = await message.answer(f"тП│ Xabar yuborilmoqda: 0/{len(users)}...")

    

    for user_id in users:

        try:

            await message.copy_to(chat_id=user_id)

            count += 1

            if count % 10 == 0: # Har 10 ta xabarda statusni yangilaymiz

                await status_msg.edit_text(f"тП│ Xabar yuborilmoqda: {count}/{len(users)}...")

            await asyncio.sleep(0.05) # Telegram limitlariga tushib qolmaslik uchun

        except TelegramForbiddenError:

            blocked += 1

        except Exception:

            pass

            

    await status_msg.edit_text(f"тЬЕ **Yuborish yakunlandi!**\n\nЁЯСд Qabul qildi: {count}\nЁЯЪл Bloklagan: {blocked}\nЁЯУК Jami: {len(users)}")



# --- FEEDBACK SYSTEM ---

@dp.callback_query(F.data == "feedback_choice")

async def feedback_btn(callback: CallbackQuery, state: FSMContext):

    await callback.answer()

    await callback.message.answer("тЬНя╕П Iltimos, o'z taklif yoki shikoyatingizni yozib qoldiring. Adminlarimiz uni albatta ko'rib chiqishadi:")

    await state.set_state(MixState.waiting_for_feedback)



@dp.message(MixState.waiting_for_feedback)

async def handle_feedback_msg(message: Message, state: FSMContext):

    await state.clear()

    # Adminga yuboramiz

    user_info = f"ЁЯСд Foydalanuvchi: {message.from_user.full_name}\nЁЯЖФ ID: `{message.from_user.id}`\nЁЯФЧ User: @{message.from_user.username or 'yoq'}"

    await bot.send_message(ADMIN_ID, f"ЁЯУй **Yangi Taklif!**\n\n{user_info}\n\nЁЯУЭ Xabar: {message.text or 'fayl yuborildi'}")

    if not message.text:

         await message.copy_to(ADMIN_ID)

         

    await message.answer("тЬЕ Rahmat! Taklifingiz qabul qilindi va adminga yetkazildi. ЁЯШК", reply_markup=main_keyboard)



# --- BOT FUNKSIYALARI ---

@dp.callback_query(F.data == "mix_choice")

async def mix_choice_btn(callback: CallbackQuery, state: FSMContext):

    await callback.answer()

    await callback.message.answer("ЁЯУ╕ Juda yaxshi! Unda birinchi **rasm** yuboring:")

    await state.set_state(MixState.waiting_for_photo)



@dp.callback_query(F.data == "down_choice")

async def down_choice_btn(callback: CallbackQuery, state: FSMContext):

    await callback.answer()

    await callback.message.answer("ЁЯФЧ Menga Instagram video havola (link) yuboring:")

    await state.set_state(MixState.waiting_for_downloader)



@dp.callback_query(F.data == "shazam_choice")

async def shazam_choice_btn(callback: CallbackQuery, state: FSMContext):

    await callback.answer()

    await callback.message.answer("ЁЯФН Audio/video fayl yoki Instagram linkini yuboring:")

    await state.set_state(MixState.waiting_for_shazam)



@dp.message(MixState.waiting_for_photo, F.photo)

async def handle_photo(message: Message, state: FSMContext):

    photo_id = message.photo[-1].file_id

    await state.update_data(photo_id=photo_id)

    await message.answer("тЬЕ Rasm tayyor!\n\nЁЯФЧ Endi audiosi bor video linkini yuboring:")

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

        return await message.answer("тЭМ Havola topilmadi.")

    

    print(f"DEBUG: Extracted URL for mix: {url}")

    data = await state.get_data()

    photo_id = data.get("photo_id")

    await state.clear()

    wait_msg = await message.answer(f"тП│ Tayyorlanmoqda...\nЁЯФЧ URL: {url[:30]}...")

    

    try:

        os.makedirs("temp", exist_ok=True)

        photo_path = f"temp/{message.from_user.id}_p.jpg"

        audio_path = f"temp/{message.from_user.id}_a.mp3"

        output_path = f"temp/{message.from_user.id}_out.mp4"

        

        await bot.download(photo_id, destination=photo_path)

        await download_audio(url, audio_path)

        mix_image_audio(photo_path, audio_path, output_path)

        

        db.log_stats(message.from_user.id, "mix")

        await message.answer_video(video=FSInputFile(output_path), caption=FINAL_CAPTION)

        

        for f in [photo_path, audio_path, output_path]:

            if os.path.exists(f): os.remove(f)

    except Exception as e:

        await message.answer(f"тЭМ Xatolik: {str(e)}")

    

    await wait_msg.delete()

    await message.answer("Menu:", reply_markup=main_keyboard)



@dp.message(MixState.waiting_for_downloader, F.text)

async def handle_download_direct(message: Message, state: FSMContext):

    url = extract_url(message.text)

    if not url:

        return await message.answer("тЭМ Havola topilmadi.")

    

    print(f"DEBUG: Extracted URL for download: {url}")

    await state.clear()

    wait_msg = await message.answer(f"ЁЯУе Yuklanmoqda...\nЁЯФЧ URL: {url[:30]}...")

    try:

        os.makedirs("temp", exist_ok=True)

        video_path = f"temp/{message.from_user.id}_d.mp4"

        await download_video(url, video_path)

        db.log_stats(message.from_user.id, "download")

        if os.path.exists(video_path):

            await message.answer_video(video=FSInputFile(video_path), caption=FINAL_CAPTION)

            os.remove(video_path)

    except Exception as e:

        await message.answer(f"тЭМ Xatolik: {str(e)}")

    await wait_msg.delete()

    await message.answer("Menu:", reply_markup=main_keyboard)



@dp.message(MixState.waiting_for_shazam)

async def handle_shazam_direct(message: Message, state: FSMContext):

    await state.clear()

    wait_msg = await message.answer("ЁЯФН Tahlil qilinmoqda...")

    try:

        os.makedirs("temp", exist_ok=True)

        temp_path = f"temp/{message.from_user.id}_s.mp3"

        if message.text:

            url = extract_url(message.text)

            if url:

                await download_audio(url, temp_path)

            else:

                return await message.answer("тЭМ Havola topilmadi.")

        elif message.audio or message.voice or message.video:

            file_id = message.audio.file_id if message.audio else (message.voice.file_id if message.voice else message.video.file_id)

            await bot.download(file_id, destination=temp_path)

        track = await identify_music(temp_path)

        db.log_stats(message.from_user.id, "shazam")

        if track:

            shazam_text = (

                f"ЁЯО╡ **{track['title']}**\nЁЯСд {track['subtitle']}\n\n"

                f"ЁЯФЧ [Shazam orqali ochish]({track['shazam_url']})\n\n"

                f"ЁЯдЦ Bot: @sadoon\_ai\_bot"

            )

            await message.answer(shazam_text)

        else:

            await message.answer("тЭМ Topilmadi.")

        if os.path.exists(temp_path): os.remove(temp_path)

    except Exception as e:

        await message.answer(f"тЭМ Xatolik: {str(e)}")

    await wait_msg.delete()

    await message.answer("Menu:", reply_markup=main_keyboard)



async def main():

    db.init_db()

    commands = [

        BotCommand(command="start", description="ЁЯПа Botni boshlash"),

        BotCommand(command="admin", description="ЁЯУК Statistika (Admin)")

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

