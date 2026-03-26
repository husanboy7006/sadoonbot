import asyncio
import os
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, FSInputFile

# ⚠️ MUHIM: Bu yerga BotFather'dan olingan bot TOKEN ni yozing!
TOKEN = "8727075082:AAEQrVaA_S-D6wHy1URANE2NgLVMs5d7yXw" 
# Bizning FastAPI Markaziy Dvigatel manzilimiz
# Agar Docker ishlatsak, u os.getenv orqali "http://api:8000/api/mix" bo'lini o'qib oladi.
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000/api/mix")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Bot foydalanuvchilarining qaysi bosqichdaligini kuzatib turadigan Holatlar
class MixState(StatesGroup):
    waiting_for_photo = State()
    waiting_for_link = State()

@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
    await message.answer(
        "👋 Salom! Men **Sadoon** botiman 🎥\n\n"
        "Menga o'zingizning biron rasmingizni yuboring, keyin esa Instagram (audio bor bo'lgan) ssilkasini bering."
        " Men audioni orqa fonga qo'yib uni tayyor videoga aylantiraman!\n\n"
        "📸 _Qani, birinchi menga rasm yuboring:_ ",
        parse_mode="Markdown"
    )
    await state.set_state(MixState.waiting_for_photo)

@dp.message(MixState.waiting_for_photo, F.photo)
async def handle_photo(message: Message, state: FSMContext):
    # Yuborilgan rasmlar ichidan eng yuqori sifatlisini (oxirgisini) tanlab id sini olamiz
    photo_id = message.photo[-1].file_id
    
    # Rasm ID sini eslab qolib, keyingi API so'rovi uchun saqlaymiz
    await state.update_data(photo_id=photo_id)
    
    await message.answer("✅ Rasm ajoyib!\n\n🔗 Endi menga Instagram (Reels) yoki boshqa shunga o'xshash audiosi bor video havolasini yuboring:")
    await state.set_state(MixState.waiting_for_link)

@dp.message(MixState.waiting_for_link, F.text)
async def handle_link(message: Message, state: FSMContext):
    url = message.text
    if "http" not in url:
        await message.answer("⚠️ Iltimos, to'g'ri havolani (ssilka - http...) yuboring:")
        return

    # Eslab qolinggan rasmni tortamiz
    data = await state.get_data()
    photo_id = data.get("photo_id")
    
    # Jarayon davomida foydalanuvchi yana xabar yubormasligi uchun holatni darhol tozalaymiz
    await state.clear()
    
    wait_msg = await message.answer("⏳ Video tayyorlanmoqda. Iltimos, ulanish, yuklash va aylantirishni tugatgunimizcha biroz kutib turing...")
    
    try:
        # Papka bo'lmasa ochamiz
        os.makedirs("temp", exist_ok=True)
        photo_path = f"temp/{message.from_user.id}_bot_photo.jpg"
        
        # 1. Rasmni Telegram serverlaridan kompyuterimizga vaqtincha saqlab olamiz
        await bot.download(photo_id, destination=photo_path)
        
        # 2. Markaziy API'mizga fayllarni yuborishga tayyorlaymiz
        form_data = aiohttp.FormData()
        form_data.add_field('url', url)
        form_data.add_field('image', open(photo_path, 'rb'), filename='photo.jpg', content_type='image/jpeg')
        
        # Server javobini kutamiz (API bilan ishlaydi!)
        async with aiohttp.ClientSession() as session:
            # So'rov yuboramiz va video tayyorlanishi ba'zida 1-2 minut olishi mumkinligi sabab 'timeout' beramiz
            async with session.post(API_URL, data=form_data, timeout=300) as response:
                result = await response.json()
                
                if result.get("status") == "success":
                    # Video muvaffaqiyatli tayyorlandi, uni foydalanuvchiga uzatamiz
                    download_url = result.get("download_url")
                    task_id = download_url.split("/")[-1]
                    
                    video_path = f"output/{task_id}_final.mp4"
                    
                    if os.path.exists(video_path):
                        await wait_msg.edit_text("✅ Video ko'rsatuvga tayyor! Jo'natmoqdaman...")
                        
                        # Telegram serveriga yuklash biroz vaqt olishi mumkin, request_timeout beramiz
                        vid_file = FSInputFile(video_path)
                        try:
                            await message.answer_video(video=vid_file, caption="Siz so'ragan video! 🎵", request_timeout=300)
                        except Exception as send_err:
                            if "timeout" not in str(send_err).lower():
                                raise send_err
                        
                        # Jo'natib bo'lgach diskni quritish (tozalash)
                        os.remove(video_path)
                    else:
                        await wait_msg.edit_text("❌ Kechirasiz, fayl serverda topilmadi.")
                else:
                    await wait_msg.edit_text(f"❌ Xatolik yuz berdi: {result.get('message')}")
                    
        # Telegramdan yuklangan oddiy rasmni ham tozalab tashlaymiz
        if os.path.exists(photo_path):
            os.remove(photo_path)
            
            
    except Exception as e:
        await wait_msg.edit_text(
            f"❌ API ga ulanishda yoxud kodda xatolik yuz berdi:\n\n{str(e)}\n\n"
            "Eslatma: **Markaziy API (FastAPI) serverini terminal orqali yoqqaningizga (run qilganingizga) ishonchingiz komilmi?**"
        )

async def main():
    print("Bot muvaffaqiyatli ishga tushdi va API bn ulanishni kutmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
