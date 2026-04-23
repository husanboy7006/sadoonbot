from fastapi import FastAPI, Request, Form, Query, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn
import mixer
import os
import uuid
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

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

# --- TELEGRAM WEBHOOK ---
bot_module = None

@app.on_event("startup")
async def on_startup():
    global bot_module
    print("[*] Loading bot module...")
    import bot as bot_module
    
    # Webhook'ni o'rnatishga harakat qilamiz
    webhook_url = f"{BASE_URL}/webhook/{bot_module.TOKEN}"
    print(f"[*] Setting webhook to: {webhook_url}")
    try:
        await bot_module.bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True
        )
        print("[*] ✅ Webhook successfully set!")
    except Exception as e:
        print(f"[!] ⚠️ Could not set webhook automatically: {e}")
        print(f"[!] Please run this command from your LOCAL machine:")
        print(f"[!] curl -X POST https://api.telegram.org/bot{bot_module.TOKEN}/setWebhook?url={webhook_url}&drop_pending_updates=true")

@app.on_event("shutdown")
async def on_shutdown():
    if bot_module:
        try:
            await bot_module.bot.session.close()
        except: pass

@app.post("/webhook/{token}")
async def webhook_handler(token: str, request: Request):
    """Telegram webhook endpoint"""
    if not bot_module:
        return JSONResponse({"error": "Bot not loaded"}, status_code=500)
    
    try:
        data = await request.json()
        from aiogram.types import Update
        update = Update.model_validate(data, context={"bot": bot_module.bot})
        await bot_module.dp.feed_update(bot=bot_module.bot, update=update)
    except Exception as e:
        print(f"[!] Webhook processing error: {e}")
    
    return JSONResponse({"ok": True})

# --- EXISTING API ENDPOINTS ---
@app.get("/")
async def read_root():
    return {"status": "Sadoon API and Bot are running (Webhook mode)", "auth_enabled": bool(SADOON_API_KEY)}

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
