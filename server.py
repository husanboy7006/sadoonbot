from fastapi import FastAPI, Request, Form, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from typing import Optional
import uvicorn
import mixer
import os
import uuid
import json
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
TOKEN = os.getenv("HF_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("API_TOKEN")

async def check_auth(x_api_key: Optional[str]):
    if SADOON_API_KEY and x_api_key != SADOON_API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized access")

# --- DATABASE ---
from database import Database
db = Database()

# --- KEYBOARD ---
MAIN_KEYBOARD = json.dumps({
    "keyboard": [
        [{"text": "🎬 Klip Yaratish (V3) (🖼️ rasm + 🎵 musiqa)"}],
        [{"text": "🚀 CGI Product Artist (Premium v2)"}],
        [{"text": "📥 Yuklab olish"}, {"text": "🔍 Shazam"}],
        [{"text": "🌐 Tilmoch AI"}, {"text": "💎 Balans"}],
        [{"text": "✍️ Takliflar"}, {"text": "💰 To'ldirish"}]
    ],
    "resize_keyboard": True
})

# --- WEBHOOK HANDLER (Javob webhook orqali qaytadi, chiquvchi ulanish kerak emas) ---
@app.post("/webhook/{token}")
async def webhook_handler(token: str, request: Request):
    data = await request.json()
    
    if "message" not in data:
        return JSONResponse({"ok": True})
    
    msg = data["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")
    user = msg.get("from", {})
    user_id = user.get("id")
    first_name = user.get("first_name", "")
    
    print(f"[*] Webhook: '{text}' from {user_id} ({first_name})")
    
    # /start
    if text == "/start":
        try: db.add_user(user_id, first_name)
        except: pass
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": f"Xush kelibsiz, {first_name}! Sadoon AI botiga xush kelibsiz. 🚀",
            "reply_markup": MAIN_KEYBOARD
        })
    
    # 💎 Balans
    if text == "💎 Balans":
        balance = db.get_balance(user_id)
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": f"💎 Sizning balansingiz: {balance} somoniy.\n🆔 ID: {user_id}"
        })
    
    # 💰 To'ldirish
    if text == "💰 To'ldirish":
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": f"💰 Balansni to'ldirish uchun adminga murojaat qiling:\n🆔 ID: {user_id}\n👤 Admin: @husanjon007"
        })
    
    # ✍️ Takliflar
    if text == "✍️ Takliflar":
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "✍️ Botni yaxshilash bo'yicha taklifingizni yozib qoldiring.\n\nTaklifingizni oddiy xabar sifatida yozing, admin ko'radi."
        })
    
    # 📥 Yuklab olish
    if text == "📥 Yuklab olish":
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "🔗 TikTok, Instagram, YouTube yoki Pinterest havolasini yuboring."
        })
    
    # 🔍 Shazam
    if text == "🔍 Shazam":
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "🎧 Musiqa parchasini (ovozli xabar, audio yoki video) yuboring."
        })
    
    # 🌐 Tilmoch AI
    if text == "🌐 Tilmoch AI":
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "✍️ Tarjima qilinadigan matnni yuboring."
        })
    
    # 🚀 CGI
    if text == "🚀 CGI Product Artist (Premium v2)":
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "📸 Reklama qilmoqchi bo'lgan mahsulotingiz rasmini yuboring."
        })
    
    # 🎬 Klip
    if text == "🎬 Klip Yaratish (V3) (🖼️ rasm + 🎵 musiqa)":
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "🖼 1-qadam: Klip uchun rasm yuboring."
        })
    
    # URL Detection (download)
    if text and ("http://" in text or "https://" in text):
        import re
        urls = re.findall(r'http[s]?://[^\s]+', text)
        if urls:
            url = urls[0].strip('.,()!?*')
            uid = str(uuid.uuid4())[:8]
            output = f"temp/v_{uid}.mp4"
            try:
                success = await mixer.download_video(url, output)
                if success:
                    db.log_stats(user_id, "download")
                    # Video faylni URL orqali yuborish
                    import shutil
                    final_path = f"output/vid_{uid}.mp4"
                    shutil.move(output, final_path)
                    return JSONResponse({
                        "method": "sendMessage",
                        "chat_id": chat_id,
                        "text": f"✅ Yuklab olindi!\n\n📥 Yuklab olish havolasi:\n{BASE_URL}/output/vid_{uid}.mp4"
                    })
                else:
                    return JSONResponse({
                        "method": "sendMessage",
                        "chat_id": chat_id,
                        "text": "❌ Yuklab bo'lmadi. Havola noto'g'ri yoki bloklangan."
                    })
            except Exception as e:
                return JSONResponse({
                    "method": "sendMessage",
                    "chat_id": chat_id,
                    "text": f"❌ Xatolik: {str(e)[:200]}"
                })
            finally:
                if os.path.exists(output): os.remove(output)
    
    # Default response
    return JSONResponse({
        "method": "sendMessage",
        "chat_id": chat_id,
        "text": "Asosiy menyu:",
        "reply_markup": MAIN_KEYBOARD
    })

# --- API ENDPOINTS ---
@app.get("/")
async def read_root():
    return {"status": "Sadoon API + Bot (Webhook Mode)", "auth_enabled": bool(SADOON_API_KEY)}

@app.post("/api/download-video")
async def api_download_video(request: Request, url: Optional[str] = Form(None), x_api_key: Optional[str] = Header(None)):
    await check_auth(x_api_key)
    if url is None:
        try: data = await request.json(); url = data.get("url")
        except: pass
    if not url: return {"status": "error", "message": "URL topilmadi"}
    uid = str(uuid.uuid4())[:8]
    output_file = f"output/vid_{uid}.mp4"
    try:
        success = await mixer.download_video(url, output_file)
        if success: return {"status": "success", "download_url": f"{BASE_URL}/output/vid_{uid}.mp4"}
        return {"status": "error", "message": "Video yuklab bo'lmadi"}
    except Exception as e: return {"status": "error", "message": str(e)}

@app.post("/api/shazam")
async def api_shazam(request: Request, url: Optional[str] = Form(None), x_api_key: Optional[str] = Header(None)):
    await check_auth(x_api_key)
    if url is None:
        try: data = await request.json(); url = data.get("url")
        except: pass
    uid = str(uuid.uuid4())[:8]
    temp_audio = f"temp/shz_{uid}.mp3"
    try:
        success = await mixer.download_audio(url, temp_audio)
        if success:
            info = await mixer.identify_music(temp_audio)
            if os.path.exists(temp_audio): os.remove(temp_audio)
            return {"status": "success", "shazam": info}
        return {"status": "error", "message": "Musiqa topilmadi"}
    except Exception as e: return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
