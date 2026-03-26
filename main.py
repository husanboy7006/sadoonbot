from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uuid
import shutil
import sys
from mixer import download_audio, mix_image_audio

# Windows uchun joriy papkada (c:\InstaMixer) joylashgan ffmpeg.exe va ffprobe.exe ni 
# tizim PATH o'zgaruvchisiga dastur ishga tushayotganda qo'shib qo'yamiz.
# Bu orqali yt-dlp va ffmpeg-python ularni bemalol topib ishlata oladi.
os.environ["PATH"] += os.pathsep + os.getcwd()

app = FastAPI(title="Sadoon API", description="Audio va Rasm Dvigateli API (Mix, Shazam...)")

# Veb-sayt (Frontend) orqali API ga muammosiz ulanish uchun CORS ni yoqamiz
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Barcha saytlardan kelgan so'rovlarga ruxsat berish
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Papkalarni yaratish (agar bo'lmasa)
os.makedirs("temp", exist_ok=True)
os.makedirs("output", exist_ok=True)

@app.get("/")
def home():
    return {"message": "InstaMixer API ishlamoqda! Ushbu tizim Insta audio + Rasm -> Video qilib beradi."}

@app.post("/api/mix")
async def mix_audio_video(
    url: str = Form(...),          # Instagram (yada boshqa) ssilka
    image: UploadFile = File(...)  # Foydalanuvchi yuborgan rasm
):
    try:
        # Noyob (unique) ID yaratish
        task_id = str(uuid.uuid4())
        
        # Fayl nomlarini tayyorlash
        image_ext = image.filename.split(".")[-1]
        image_path = f"temp/{task_id}_image.{image_ext}"
        audio_path = f"temp/{task_id}_audio.mp3"
        output_path = f"output/{task_id}_final.mp4"

        # 1. Rasmni diskga vaqtincha saqlab qolish
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        
        # 2. Instagram ssilkasidan audioni mp3 qilib tortish
        download_audio(url, audio_path)
        
        # 3. Yana o'sha audioni haligi rasm bilan qo'shish
        mix_image_audio(image_path, audio_path, output_path)
        
        # Tozalash - jarayon tugagach oddiy rasm va audioni udalit qilish 
        # (server xotirasi to'lmasligi uchun)
        if os.path.exists(image_path): os.remove(image_path)
        if os.path.exists(audio_path): os.remove(audio_path)
            
        return {
            "status": "success", 
            "message": "Video muvaffaqiyatli yaratildi", 
            "download_url": f"/download/{task_id}"
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/download/{task_id}")
async def get_video(task_id: str):
    file_path = f"output/{task_id}_final.mp4"
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename=f"instamix_{task_id}.mp4", media_type='video/mp4')
    return {"error": "Fayl topilmadi yoki yaratishda xato bo'ldi"}

# Serverni ishga tushirish uchun komanda:
# uvicorn main:app --reload
