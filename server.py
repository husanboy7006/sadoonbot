from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import mixer
import os
import uuid

app = FastAPI()

# CORS sozlamalari - barcha turdagi so'rovlar uchun ochiq
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

# Relative URL emas, Full URL qaytarish uchun Space manzilini aniqlaymiz
# Hugging Face da bu odatda 'https://user-space.hf.space' ko'rinishida bo'ladi
BASE_URL = "https://husanjon007-sadoon-api.hf.space"

# Static fayllarni ulash
app.mount("/output", StaticFiles(directory="output"), name="output")

class MixRequest(BaseModel):
    url: str
    image_url: str = None

@app.get("/")
async def read_root():
    return {"status": "Sadoon API and Bot are running", "cors": "enabled"}

# 1. Download Video (Frontend 'download-video' deb so'raydi)
@app.get("/api/download-video")
async def api_download_video(url: str = Query(...)):
    uid = str(uuid.uuid4())[:8]
    output_file = f"output/vid_{uid}.mp4"
    print(f"[*] GET Download request for: {url[:30]}")
    try:
        success = await mixer.download_video(url, output_file)
        if success:
            return {
                "status": "success", 
                "message": "Tayyor!", 
                "download_url": f"{BASE_URL}/output/vid_{uid}.mp4"
            }
        return {"status": "error", "message": "Yuklab bo'lmadi (Scraper error)"}
    except Exception as e:
        print(f"[-] API Error: {e}")
        return {"status": "error", "message": str(e)}

# 2. Mix (Frontend POST orqali yuboradi)
@app.post("/api/mix")
async def api_mix(req: MixRequest):
    uid = str(uuid.uuid4())[:8]
    url = req.url
    print(f"[*] POST Mix request for: {url[:30]}")
    output_file = f"output/mix_{uid}.mp4"
    try:
        # Hozircha mix o'rniga oddiy yuklab qaytaramiz (Frontend kutayotganidek)
        success = await mixer.download_video(url, output_file)
        if success:
            return {
                "status": "success", 
                "message": "Tayyor!", 
                "download_url": f"{BASE_URL}/output/mix_{uid}.mp4"
            }
        return {"status": "error", "message": "Bazadan xatolik qaytdi"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 3. Shazam (Frontend GET orqali so'raydi)
@app.get("/api/shazam")
async def api_shazam(url: str = Query(...)):
    uid = str(uuid.uuid4())[:8]
    temp_audio = f"temp/shz_{uid}.mp3"
    print(f"[*] GET Shazam request for: {url[:30]}")
    try:
        success = await mixer.download_audio(url, temp_audio)
        if success:
            info = await mixer.identify_music(temp_audio)
            if os.path.exists(temp_audio): os.remove(temp_audio)
            return {"status": "success", "message": "Topildi!", "shazam": info}
        return {"status": "error", "message": "Musiqa topilmadi"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
