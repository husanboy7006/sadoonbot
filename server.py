from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import mixer
import os
import uuid
import asyncio

app = FastAPI()

# CORS sozlamalari
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fayllarni yuklab olish uchun URL (Static files)
# HF da filelar /app/output yoki /app/temp dagi fayllarni ko'ra oladi
if not os.path.exists("output"): os.makedirs("output")
app.mount("/output", StaticFiles(directory="output"), name="output")

class MixRequest(BaseModel):
    url: str
    type: str = "download" # 'download' or 'shazam' or 'mix'
    image_url: str = None

@app.get("/")
def read_root():
    return {"status": "Sadoon API and Bot are running"}

@app.post("/api/mix")
async def api_mix(req: MixRequest):
    """Vercel saytidan keladigan yuklash va mix qilish so'rovlari uchun"""
    url = req.url
    type = req.type
    uid = str(uuid.uuid4())[:8]
    
    print(f"[*] API so'rov: {type} -> {url[:30]}...")

    try:
        if type == "download":
            # Oddiy video yuklash
            output_file = f"output/video_{uid}.mp4"
            success = await mixer.download_video(url, output_file)
            if success:
                # HF dagi to'g'ridan to'g'ri link (HF Space URL ga asoslanadi)
                # Space nomini dinamik bilish qiyin, lekin relative path ishlaydi
                download_url = f"/output/video_{uid}.mp4"
                return {"status": "success", "download_url": download_url}
        
        elif type == "shazam":
            # Shazam orqali aniqlash
            temp_audio = f"temp/audio_{uid}.mp3"
            success = await mixer.download_audio(url, temp_audio)
            if success:
                info = await mixer.identify_music(temp_audio)
                if os.path.exists(temp_audio): os.remove(temp_audio)
                return {"status": "success", "shazam": info}
        
        return {"status": "error", "message": "Noma'lum tur yoki yuklab bo'lmadi"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
