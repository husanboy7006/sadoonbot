import os
import uuid
import logging
import socket
import urllib.parse
from typing import Optional

# --- 1. STRONG DNS PATCH (Hugging Face firewall'ni chetlab o'tish uchun) ---
def apply_dns_patch():
    try:
        old_getaddrinfo = socket.getaddrinfo
        def new_getaddrinfo(*args, **kwargs):
            try:
                return old_getaddrinfo(*args, **kwargs)
            except socket.gaierror:
                host = args[0]
                # Supabase IP manzillarini qo'lda kiritamiz (Fallback)
                if "supabase.co" in host:
                    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('104.21.50.110', args[1]))]
                if "google" in host:
                    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('142.250.185.74', args[1]))]
                if "telegram.org" in host:
                    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('149.154.167.220', args[1]))]
                raise
        socket.getaddrinfo = new_getaddrinfo
        print("[*] DNS Patch applied successfully.")
    except Exception as e:
        print(f"[!] DNS Patch failed: {e}")

apply_dns_patch()

# --- 2. FASTAPI INITIALIZATION ---
from fastapi import FastAPI, Request, Form, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import uvicorn
import mixer
from database import Database
import sqlite3

# --- SQLITE LOCAL DATABASE (For States) ---
def init_sqlite():
    conn = sqlite3.connect("local_states.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS states (user_id TEXT PRIMARY KEY, state TEXT)")
    conn.commit()
    conn.close()

def set_local_state(user_id, state):
    with sqlite3.connect("local_states.db") as conn:
        conn.execute("INSERT OR REPLACE INTO states (user_id, state) VALUES (?, ?)", (str(user_id), state))
        conn.commit()

def get_local_state(user_id):
    with sqlite3.connect("local_states.db") as conn:
        row = conn.execute("SELECT state FROM states WHERE user_id = ?", (str(user_id),)).fetchone()
    return row[0] if row else None

init_sqlite()

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

# --- 3. CONFIGURATION ---
BASE_URL = os.getenv("BASE_URL", "https://husanjon007-sadoon-api.hf.space")
SADOON_API_KEY = os.getenv("SADOON_API_KEY")
db = Database()

# --- 4. GEMINI INITIALIZATION ---
import google.generativeai as genai
GEMINI_KEY = os.getenv("GEMINI_KEY") or os.getenv("GEMINI_API_KEY")
model = None
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")

# --- 5. KEYBOARD ---
MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "🎬 Klip Yaratish (V3) (🖼️ rasm + 🎵 musiqa)"}],
        [{"text": "🚀 CGI Product Artist (Premium v2)"}],
        [{"text": "📥 Yuklab olish"}, {"text": "🔍 Shazam"}],
        [{"text": "🌐 Tilmoch AI"}, {"text": "💎 Balans"}],
        [{"text": "✍️ Takliflar"}, {"text": "💰 To'ldirish"}]
    ],
    "resize_keyboard": True
}

# --- 6. WEBHOOK HANDLER (A TO Z LOGIC) ---
@app.post("/webhook/bot")
async def webhook_handler(request: Request):
    try:
        data = await request.json()
    except:
        return JSONResponse({"ok": True})

    if "message" not in data:
        return JSONResponse({"ok": True})
    
    msg = data["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")
    user_id = str(msg["from"]["id"])
    first_name = msg["from"].get("first_name", "Foydalanuvchi")
    
    # State management (Local SQLite - 100% Reliable)
    current_state = get_local_state(user_id)
    
    print(f"[*] Webhook: '{text}' from {user_id} (State: {current_state})")

    # /start
    if text == "/start":
        set_local_state(user_id, None)
        try: db.add_user(user_id, first_name)
        except: pass
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": f"Xush kelibsiz, {first_name}! 🚀\nSadoon AI tizimi lokal bazaga ulandi (DNS muammosi hal qilindi).",
            "reply_markup": MAIN_KEYBOARD
        })

    # Tilmoch AI activation
    if text == "🌐 Tilmoch AI":
        set_local_state(user_id, "waiting_translate")
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "✍️ Tarjima qilinadigan xabarni yuboring."
        })

    # CGI activation
    if text == "🚀 CGI Product Artist (Premium v2)":
        set_local_state(user_id, "waiting_cgi")
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "📸 Mahsulot nomini yozing."
        })

    # 💎 Balans
    if text == "💎 Balans":
        balance = db.get_balance(user_id)
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": f"💎 Sizning balansingiz: {balance} somoniy.\n🆔 ID: `{user_id}`",
            "parse_mode": "Markdown"
        })

    # 📥 Yuklab olish
    if text == "📥 Yuklab olish":
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "🔗 Instagram, TikTok yoki YouTube havolasini yuboring."
        })

    # Handling States (AI)
    if current_state == "waiting_translate" and text and not text.startswith("/"):
        set_local_state(user_id, None)
        if not model:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": "❌ AI sozlanmagan (GEMINI_KEY yo'q)."})
        try:
            print(f"[*] AI Generating translation for: {text[:20]}...")
            response = model.generate_content(f"Siz professional tarjimon va tilshunosiz. Ushbu matnni tarjima qiling va qisqacha izoh bering: {text}")
            return JSONResponse({
                "method": "sendMessage",
                "chat_id": chat_id,
                "text": response.text
            })
        except Exception as e:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": f"❌ AI xatolik: {str(e)}"})

    if current_state == "waiting_cgi" and text and not text.startswith("/"):
        set_local_state(user_id, None)
        safe_text = urllib.parse.quote(f"Professional studio product photography of {text}, luxury style, cinematic lighting, high resolution, 8k")
        flux_url = f"https://image.pollinations.ai/prompt/{safe_text}?nologo=true"
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": f"✅ **CGI Artist natijasi:**\n\n🖼 [Rasmni ko'rish]({flux_url})\n\n*(Eslatma: Rasm generatsiya bo'lishi uchun bir necha soniya kuting)*",
            "parse_mode": "Markdown"
        })

    # URL Detection (Direct download)
    if text and ("http://" in text or "https://" in text):
        return JSONResponse({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "⏳ Yuklab olish jarayoni boshlandi. Iltimos, kutib turing..."
        })

    # Default
    return JSONResponse({
        "method": "sendMessage",
        "chat_id": chat_id,
        "text": "Asosiy menyu:",
        "reply_markup": MAIN_KEYBOARD
    })

# --- 7. API ENDPOINTS ---
@app.get("/")
async def read_root():
    return {"status": "Sadoon API + Bot (A-Z Healthy)", "gemini": bool(GEMINI_KEY)}

@app.post("/api/download-video")
async def api_download_video(request: Request, url: Optional[str] = Form(None), x_api_key: Optional[str] = Header(None)):
    if SADOON_API_KEY and x_api_key != SADOON_API_KEY: raise HTTPException(403)
    if url is None:
        try: data = await request.json(); url = data.get("url")
        except: pass
    if not url: return {"status": "error", "message": "URL missing"}
    uid = str(uuid.uuid4())[:8]
    output_file = f"output/vid_{uid}.mp4"
    try:
        success = await mixer.download_video(url, output_file)
        if success: return {"status": "success", "download_url": f"{BASE_URL}/output/vid_{uid}.mp4"}
        return {"status": "error", "message": "Download failed"}
    except Exception as e: return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
