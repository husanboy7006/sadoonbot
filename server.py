from fastapi import FastAPI, Request, BackgroundTasks, Query
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

# Papkalarni tekshirish
if not os.path.exists("output"): os.makedirs("output")
if not os.path.exists("temp"): os.makedirs("temp")
app.mount("/output", StaticFiles(directory="output"), name="output")

class MixRequest(BaseModel):
    url: str
    image_url: str = None

@app.get("/")
def read_root():
    return {"status": "Sadoon API and Bot are running"}

# 1. Download Video Endpoint (GET or POST based on Vercel script)
@app.get("/api/download-video")
async def api_download_video(url: str = Query(...)):
    uid = str(uuid.uuid4())[:8]
    output_file = f"output/video_{uid}.mp4"
    print(f"[*] API Download: {url[:30]}")
    try:
        success = await mixer.download_video(url, output_file)
        if success:
            return {"status": "success", "download_url": f"/output/video_{uid}.mp4"}
        return {"status": "error", "message": "Video yuklab bo'lmadi"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 2. Mix Endpoint (POST)
@app.post("/api/mix")
async def api_mix(req: MixRequest):
    uid = str(uuid.uuid4())[:8]
    url = req.url
    print(f"[*] API Mix: {url[:30]}")
    # Hozircha mix funksiyasi soddalashtirilgan (faqat downloader kabi ishlaydi yoki mix qiladi)
    # Agar frontend faqat buni ishlatsa, shuni qaytaramiz
    output_file = f"output/mix_{uid}.mp4"
    try:
        success = await mixer.download_video(url, output_file)
        if success:
            return {"status": "success", "download_url": f"/output/mix_{uid}.mp4"}
        return {"status": "error", "message": "Mix qilib bo'lmadi"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 3. Shazam Endpoint (GET)
@app.get("/api/shazam")
async def api_shazam(url: str = Query(...)):
    uid = str(uuid.uuid4())[:8]
    temp_audio = f"temp/shazam_{uid}.mp3"
    print(f"[*] API Shazam: {url[:30]}")
    try:
        success = await mixer.download_audio(url, temp_audio)
        if success:
            info = await mixer.identify_music(temp_audio)
            if os.path.exists(temp_audio): os.remove(temp_audio)
            return {"status": "success", "shazam": info}
        return {"status": "error", "message": "Musiqa aniqlab bo'lmadi"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
