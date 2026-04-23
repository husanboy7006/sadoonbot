from fastapi import FastAPI, Request, Form, Query, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import uvicorn
import mixer
import os
import uuid
import socket

# --- UNIVERSAL DNS PATCH FOR HUGGING FACE ---
def apply_dns_patch():
    old_getaddrinfo = socket.getaddrinfo
    def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if host == "api.telegram.org":
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('149.154.167.220', port))]
        return old_getaddrinfo(host, port, family, type, proto, flags)
    socket.getaddrinfo = patched_getaddrinfo

apply_dns_patch()

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

BASE_URL = os.getenv("BASE_URL", "https://husanjon007-sadoon-api.hf.space")
SADOON_API_KEY = os.getenv("SADOON_API_KEY")

async def check_auth(x_api_key: Optional[str]):
    if SADOON_API_KEY and x_api_key != SADOON_API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized access")

@app.get("/")
async def read_root():
    return {"status": "Sadoon API and Bot are running", "auth_enabled": bool(SADOON_API_KEY)}

@app.post("/api/download-video")
async def api_download_video(request: Request, url: Optional[str] = Form(None), x_api_key: Optional[str] = Header(None)):
    await check_auth(x_api_key)
    
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
async def api_mix(request: Request, url: Optional[str] = Form(None), x_api_key: Optional[str] = Header(None)):
    await check_auth(x_api_key)
    
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
async def api_shazam(request: Request, url: Optional[str] = Form(None), x_api_key: Optional[str] = Header(None)):
    await check_auth(x_api_key)
    
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
