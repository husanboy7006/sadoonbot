import asyncio
import os
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from mixer import download_audio, mix_image_audio, identify_music, download_video
import database as db

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties

TOKEN = "8727075082:AAEQrVaA_S-D6wHy1URANE2NgLVMs5d7yXw" 
API_URL = os.getenv("API_URL", "http://127.0.0.1:7860/api/mix")

# Cloud muhiti uchun session va timeout ni moslaymiz
session = AiohttpSession(
    timeout=60,  # 60 sekund timeout
)

bot = Bot(
    token=TOKEN, 
    session=session,
    default=DefaultBotProperties(parse_mode='Markdown')
)
dp = Dispatcher()

class MixState(StatesGroup):
    waiting_for_photo = State()
    waiting_for_link = State()
    waiting_for_downloader = State()
    waiting_for_shazam = State()

# Asosiy tugmalar (Menu)
main_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🎬 Video yasash", callback_data="mix_choice")],
    [
        InlineKeyboardButton(text="🔍 Musiqani topish", callback_data="shazam_choice"),
        InlineKeyboardButton(text="📥 Videoni yuklash", callback_data="down_choice")
    ]
])

ADMIN_ID = 7110271171  # Haqiqiy Admin ID ulandi

@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
    # Foydalanuvchini bazaga qo'shish
    db.add_user(message.from_user.id, message.from_user.username)
    
    await message.answer(
        "👋 Salom! Men **Sadoon** botiman 🎥\n\nNima qilmoqchimiz? Tanlang:",
        reply_markup=main_keyboard,
        parse_mode="Markdown"
    )
    await state.clear()

@dp.message(F.text == "/admin")
async def admin_stats_handler(message: Message):
    if message.from_user.id == ADMIN_ID:
        report = db.get_stats_report()
        await message.answer(report, parse_mode="Markdown")
    else:
        await message.answer("❌ Bu buyruq faqat Admin uchun!")

@dp.message(F.text == "/my_id")
async def my_id_handler(message: Message):
    await message.answer(f"Sizning ID: `{message.from_user.id}`", parse_mode="Markdown")

@dp.callback_query(F.data == "mix_choice")
async def mix_choice_btn(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("📸 Juda yaxshi! Unda birinchi **rasm** yuboring:")
    await state.set_state(MixState.waiting_for_photo)

@dp.callback_query(F.data == "down_choice")
async def down_choice_btn(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("🔗 Menga Instagram (Reels) linkini yuboring, uni yuklab beraman:")
    await state.set_state(MixState.waiting_for_downloader)

@dp.callback_query(F.data == "shazam_choice")
async def shazam_choice_btn(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("🔍 Menga audio/video fayl yoki Instagram linkini yuboring, musiqasini topaman:")
    await state.set_state(MixState.waiting_for_shazam)

@dp.message(MixState.waiting_for_photo, F.photo)
async def handle_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo_id=photo_id)
    await message.answer("✅ Rasm ajoyib!\n\n🔗 Endi menga audiosi bor video havolasini (link) yuboring:")
    await state.set_state(MixState.waiting_for_link)

@dp.message(MixState.waiting_for_link, F.text.contains("http"))
async def handle_mix_link(message: Message, state: FSMContext):
    url = message.text
    data = await state.get_data()
    photo_id = data.get("photo_id")
    await state.clear()
    
    wait_msg = await message.answer("⏳ Video tayyorlanmoqda, iltimos kuting...")
    try:
        os.makedirs("temp", exist_ok=True)
        photo_path = f"temp/{message.from_user.id}_p.jpg"
        await bot.download(photo_id, destination=photo_path)
        # Statistika yozamiz
        db.log_stats(message.from_user.id, "mix")
        
        form_data = aiohttp.FormData()
        form_data.add_field('url', url)
        form_data.add_field('image', open(photo_path, 'rb'), filename='photo.jpg', content_type='image/jpeg')
        
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, data=form_data, timeout=300) as response:
                result = await response.json()
                if result.get("status") == "success":
                    video_path = f"output/{result.get('download_url').split('/')[-1]}_final.mp4"
                    if os.path.exists(video_path):
                        await message.answer_video(video=FSInputFile(video_path), caption="Tayyor! 🎥")
                        os.remove(video_path)
                    else:
                        await message.answer("❌ Fayl topilmadi.")
                else:
                    await message.answer(f"❌ Xato: {result.get('message')}")
        os.remove(photo_path)
    except Exception as e:
        await message.answer(f"❌ Xatolik: {str(e)}")
    
    await wait_msg.delete()
    # Amal tugadi, menuni yana chiqaramiz:
    await message.answer("Yana biron nima qilamizmi? 👇", reply_markup=main_keyboard)

@dp.message(MixState.waiting_for_downloader, F.text.contains("http"))
async def handle_download_direct(message: Message, state: FSMContext):
    url = message.text
    await state.clear()
    wait_msg = await message.answer("📥 Video yuklanmoqda...")
    try:
        os.makedirs("temp", exist_ok=True)
        video_path = f"temp/{message.from_user.id}_d.mp4"
        download_video(url, video_path)
        # Statistika yozamiz
        db.log_stats(message.from_user.id, "download")
        if os.path.exists(video_path):
            await message.answer_video(video=FSInputFile(video_path), caption="Mana video! 📥")
            os.remove(video_path)
        else:
            await message.answer("❌ Yuklab bo'lmadi.")
    except Exception as e:
        await message.answer(f"❌ Xato: {str(e)}")
    
    await wait_msg.delete()
    await message.answer("Yana biron nima qilamizmi? 👇", reply_markup=main_keyboard)

@dp.message(MixState.waiting_for_shazam)
async def handle_shazam_direct(message: Message, state: FSMContext):
    await state.clear()
    wait_msg = await message.answer("🔍 Musiqa tahlil qilinmoqda...")
    try:
        os.makedirs("temp", exist_ok=True)
        temp_path = f"temp/{message.from_user.id}_s.mp3"
        
        if message.text and "http" in message.text:
            download_audio(message.text, temp_path)
        elif message.audio or message.voice or message.video:
            file_id = message.audio.file_id if message.audio else (message.voice.file_id if message.voice else message.video.file_id)
            await bot.download(file_id, destination=temp_path)
        
        track = await identify_music(temp_path)
        # Statistika yozamiz
        db.log_stats(message.from_user.id, "shazam")
        if track:
            cap = f"🎵 **{track['title']}**\n👤 {track['subtitle']}\n\n🔗 [Shazam]({track['shazam_url']})"
            if track['image']:
                await message.answer_photo(photo=track['image'], caption=cap, parse_mode="Markdown")
            else:
                await message.answer(cap, parse_mode="Markdown")
        else:
            await message.answer("❌ Topilmadi.")
        if os.path.exists(temp_path): os.remove(temp_path)
    except Exception as e:
        await message.answer(f"❌ Xato: {str(e)}")
    
    await wait_msg.delete()
    await message.answer("Yana biron nima qilamizmi? 👇", reply_markup=main_keyboard)

async def main():
    # Bazani tayyorlaymiz
    db.init_db()
    print("Bot muvaffaqiyatli ishga tushdi...")
    # Kutib qolgan xabarlarni tozalab, botni toza holatda ishga tushiramiz
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
