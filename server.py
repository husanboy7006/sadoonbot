from fastapi import FastAPI, Request, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import uvicorn
import mixer
import os
import uuid

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not os.path.exists("output"): os.makedirs("output")
if not os.path.exists("temp"): os.makedirs("temp")
app.mount("/output", StaticFiles(directory="output"), name="output")

BASE_URL = "https://husanjon007-sadoon-api.hf.space"

class MixRequest(BaseModel):
    url: str
    image_url: Optional[str] = None

@app.get("/")
async def read_root():
    return {"status": "Sadoon API and Bot are running"}

# Vercel sayti POST yuboryapti, shuning uchun barchasini POST qilamiz
# FormData va JSON ikkalasini ham qo'llab-quvvatlaymiz

@app.post("/api/download-video")
async def api_download_video(request: Request, url: Optional[str] = Form(None)):
    # Agar FormData bo'lmasa, JSON dan qidiramiz
    if url is None:
        try:
            data = await request.json()
            url = data.get("url")
        except: pass
    
    if not url:
        return {"status": "error", "message": "URL topilmadi"}

    uid = str(uuid.uuid4())[:8]
    output_file = f"output/vid_{uid}.mp4"
    print(f"[*] API Download (POST): {url[:30]}")
    try:
        success = await mixer.download_video(url, output_file)
        if success:
            return {"status": "success", "message": "Tayyor!", "download_url": f"{BASE_URL}/output/vid_{uid}.mp4"}
        return {"status": "error", "message": "Video yuklab bo'lmadi (Bloklangan bo'lishi mumkin)"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/mix")
async def api_mix(request: Request, url: Optional[str] = Form(None)):
    if url is None:
        try:
            data = await request.json()
            url = data.get("url")
        except: pass
        
    uid = str(uuid.uuid4())[:8]
    output_file = f"output/mix_{uid}.mp4"
    print(f"[*] API Mix (POST): {url[:30]}")
    try:
        success = await mixer.download_video(url, output_file)
        if success:
            return {"status": "success", "message": "Mix tayyor!", "download_url": f"{BASE_URL}/output/mix_{uid}.mp4"}
        return {"status": "error", "message": "Mix xatoligi"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/shazam")
async def api_shazam(request: Request, url: Optional[str] = Form(None)):
    if url is None:
        try:
            data = await request.json()
            url = data.get("url")
        except: pass

    uid = str(uuid.uuid4())[:8]
    temp_audio = f"temp/shz_{uid}.mp3"
    print(f"[*] API Shazam (POST): {url[:30]}")
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
