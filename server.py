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

# --- GEMINI INITIALIZATION ---
import google.generativeai as genai
GEMINI_KEY = os.getenv("GEMINI_KEY") or os.getenv("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# --- SIMPLE STATE MANAGEMENT (In-memory) ---
user_states = {}

# --- WEBHOOK HANDLER ---
@app.post("/webhook/{token}")
async def webhook_handler(token: str, request: Request):
    data = await request.json()
    if "message" not in data:
        return JSONResponse({"ok": True})
    
    msg = data["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")
    user_id = str(msg["from"]["id"])
    first_name = msg["from"].get("first_name", "")
    
    print(f"[*] Webhook: '{text}' from {user_id}")

    # State check
    current_state = user_states.get(user_id)

    # /start
    if text == "/start":
        user_states[user_id] = None
        try: db.add_user(user_id, first_name)
        except: pass
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": f"Xush kelibsiz, {first_name}! Sadoon AI botiga xush kelibsiz. 🚀\n\nYangi API tizimi ishga tushirildi.",
            "reply_markup": MAIN_KEYBOARD
        })

    # Tilmoch AI activation
    if text == "🌐 Tilmoch AI":
        user_states[user_id] = "waiting_translate"
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "✍️ Tarjima qilinadigan xabarni yuboring."
        })

    # CGI activation
    if text == "🚀 CGI Product Artist (Premium v2)":
        user_states[user_id] = "waiting_cgi"
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "📸 Reklama qilmoqchi bo'lgan mahsulotingiz nomini yozing (Hozircha faqat matnli CGI promp ishlaydi)."
        })

    # Handling States
    if current_state == "waiting_translate" and text:
        user_states[user_id] = None
        try:
            response = model.generate_content(f"Siz professional tarjimon va tilshunosiz. Ushbu matnni tarjima qiling va qisqacha izoh bering: {text}")
            return JSONResponse({
                "method": "sendMessage",
                "chat_id": chat_id,
                "text": response.text
            })
        except Exception as e:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": f"❌ AI xatolik: {str(e)}"})

    if current_state == "waiting_cgi" and text:
        user_states[user_id] = None
        try:
            flux_url = f"https://image.pollinations.ai/prompt/Professional studio product photography of {text}, luxury style, cinematic lighting, high resolution, 8k?nologo=true"
            return JSONResponse({
                "method": "sendMessage",
                "chat_id": chat_id,
                "text": f"✅ **CGI Artist natijasi:**\n\n🖼 [Rasmni yuklab olish]({flux_url})",
                "parse_mode": "Markdown"
            })
        except Exception as e:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": f"❌ CGI xatolik: {str(e)}"})

    # 💎 Balans
    if text == "💎 Balans":
        balance = db.get_balance(user_id)
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": f"💎 Sizning balansingiz: {balance} somoniy.\n🆔 ID: `{user_id}`",
            "parse_mode": "Markdown"
        })

    # Default
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
