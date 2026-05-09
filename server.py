import os
import uuid
import asyncio
import logging
import socket
import aiohttp
from typing import Optional
import threading

# --- 1. DNS PATCH ---
def apply_dns_patch():
    try:
        old_getaddrinfo = socket.getaddrinfo
        def new_getaddrinfo(*args, **kwargs):
            try:
                return old_getaddrinfo(*args, **kwargs)
            except socket.gaierror:
                host = args[0]
                if "supabase.co" in host:
                    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('104.21.50.110', args[1]))]
                if "google" in host:
                    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('142.250.185.74', args[1]))]
                if "telegram.org" in host:
                    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('149.154.167.220', args[1]))]
                raise
        socket.getaddrinfo = new_getaddrinfo
        print("[*] DNS Patch applied.")
    except Exception as e:
        print(f"[!] DNS Patch failed: {e}")

apply_dns_patch()

# --- 2. FASTAPI ---
from fastapi import FastAPI, Request, Header, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import uvicorn
import mixer
from database import Database
import sqlite3
import threading

# --- 3. SQLITE STATE (user_id, state, state_data) ---
sqlite_lock = threading.Lock()

def init_sqlite():
    with sqlite_lock:
        with sqlite3.connect("local_states.db") as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS states (user_id TEXT PRIMARY KEY, state TEXT, data TEXT)")
            try:
                conn.execute("ALTER TABLE states ADD COLUMN data TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            except Exception as e:
                print(f"[!] SQLite init error: {e}")
            conn.commit()

def set_state(user_id, state, data=""):
    with sqlite_lock:
        with sqlite3.connect("local_states.db") as conn:
            conn.execute("INSERT OR REPLACE INTO states VALUES (?,?,?)", (str(user_id), state, data))
            conn.commit()

def get_state(user_id):
    with sqlite_lock:
        with sqlite3.connect("local_states.db") as conn:
            row = conn.execute("SELECT state, data FROM states WHERE user_id=?", (str(user_id),)).fetchone()
    return (row[0], row[1]) if row else (None, "")

init_sqlite()

logging.basicConfig(filename='server.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

if not os.path.exists("output"): os.makedirs("output")
if not os.path.exists("temp"): os.makedirs("temp")
app.mount("/output", StaticFiles(directory="output"), name="output")

# --- 4. CONFIG ---
BASE_URL = os.getenv("BASE_URL", "http://localhost:7860")
SADOON_API_KEY = os.getenv("SADOON_API_KEY")
BOT_TOKEN = os.getenv("HF_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("API_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
if not ADMIN_ID:
    print("❌ ADMIN_ID environment variable not set!")
    exit(1)
ADMIN_ID = int(ADMIN_ID)
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
db = Database()

# --- 5. GEMINI ---
from google import genai as google_genai
GEMINI_KEY = os.getenv("GEMINI_KEY") or os.getenv("GEMINI_API_KEY")
ai_client = None
if GEMINI_KEY:
    ai_client = google_genai.Client(api_key=GEMINI_KEY)

# --- 6. KEYBOARD ---
MAIN_KB = {
    "keyboard": [
        [{"text": "🎬 Klip Yaratish (V3) (🖼️ rasm + 🎵 musiqa)"}],
        [{"text": "📥 Yuklab olish"}, {"text": "🔍 Shazam"}],
        [{"text": "💎 Balans"}],
        [{"text": "✍️ Takliflar"}, {"text": "💰 To'ldirish"}]
    ],
    "resize_keyboard": True
}

# --- 7. TELEGRAM HELPERS ---
_TG_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=15)

async def tg(method, **kwargs):
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=_TG_TIMEOUT) as s:
                async with s.post(f"{TG_API}/{method}", json=kwargs) as r:
                    return await r.json()
        except Exception as e:
            print(f"[TG] {method} attempt {attempt+1} failed: {e}")
            if attempt < 2:
                await asyncio.sleep(3)
    return {}

async def tg_send(chat_id, text, **kwargs):
    await tg("sendMessage", chat_id=chat_id, text=text[:4000], **kwargs)

async def tg_send_file(method, chat_id, path, field, **kwargs):
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120, connect=15)) as s:
                with open(path, "rb") as f:
                    data = aiohttp.FormData()
                    data.add_field("chat_id", str(chat_id))
                    data.add_field(field, f, filename=os.path.basename(path))
                    for k, v in kwargs.items():
                        data.add_field(k, str(v))
                    async with s.post(f"{TG_API}/{method}", data=data) as r:
                        return await r.json()
        except Exception as e:
            print(f"[TG] {method} file attempt {attempt+1} failed: {e}")
            if attempt < 2:
                await asyncio.sleep(3)
    return {}

async def tg_download(file_id, save_path):
    async with aiohttp.ClientSession(timeout=_TG_TIMEOUT) as s:
        async with s.get(f"{TG_API}/getFile?file_id={file_id}") as r:
            info = await r.json()
        fp = info["result"]["file_path"]
        async with s.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{fp}") as r:
            with open(save_path, "wb") as f:
                f.write(await r.read())

# --- 8. BACKGROUND TASKS ---
async def _cleanup_file(path, delay=60):
    await asyncio.sleep(delay)
    try:
        if os.path.exists(path): os.remove(path)
    except: pass

async def bg_download(chat_id, url):
    output = f"output/v_{uuid.uuid4()}.mp4"
    try:
        print(f"[BG] Downloading: {url[:50]}")
        success = await asyncio.wait_for(
            mixer.download_video(url, output), timeout=90
        )
        print(f"[BG] Download result: {success}")
        if success:
            await tg_send_file("sendVideo", chat_id, output, "video")
        else:
            await tg_send(chat_id, "❌ Yuklab bo'lmadi. Boshqa havola yoki TikTok/YouTube sinab ko'ring.")
    except asyncio.TimeoutError:
        await tg_send(chat_id, "⏰ Vaqt tugadi (90s). Havola juda katta yoki bloklanган.")
    except Exception as e:
        print(f"[BG] Download error: {e}")
        await tg_send(chat_id, f"❌ Xatolik: {e}")
    finally:
        if os.path.exists(output): os.remove(output)

async def bg_shazam(chat_id, file_id):
    await tg_send(chat_id, "❌ Shazam vaqtincha ishlamaydi.")
    # temp = f"temp/shz_{uuid.uuid4()}.mp3"
    # wait_id = None
    # try:
    #     wait = await tg("sendMessage", chat_id=chat_id, text="🔍 Musiqa aniqlanmoqda...")
    #     wait_id = wait.get("result", {}).get("message_id")
    #     await tg_download(file_id, temp)
    #     info = await mixer.identify_music(temp)
    #     if info:
    #         text = f"✅ Topildi!\n🎵 {info['title']}\n👤 {info['subtitle']}"
    #     else:
    #         text = "❌ Musiqa topilmadi."
    #     await tg_send(chat_id, text)
    #     except Exception as e:
    #         await tg_send(chat_id, f"❌ Shazam xatosi: {e}")
    #     finally:
    #         if wait_id:
    #             try: await tg("deleteMessage", chat_id=chat_id, message_id=wait_id)
    #             except: pass
    #         if os.path.exists(temp): os.remove(temp)

async def bg_clip(chat_id, photo_id, audio_id):
    p = f"temp/p_{uuid.uuid4()}.jpg"
    a = f"temp/a_{uuid.uuid4()}.mp3"
    v = f"output/v_{uuid.uuid4()}.mp4"
    wait_id = None
    try:
        wait = await tg("sendMessage", chat_id=chat_id, text="🎬 Klip tayyorlanmoqda...")
        wait_id = wait.get("result", {}).get("message_id")
        await tg_download(photo_id, p)
        await tg_download(audio_id, a)
        if await mixer.mix_image_audio(p, a, v):
            await tg_send_file("sendVideo", chat_id, v, "video")
        else:
            await tg_send(chat_id, "❌ Klip yaratishda xatolik.")
    except Exception as e:
        await tg_send(chat_id, f"❌ Xato: {e}")
    finally:
        if wait_id:
            try: await tg("deleteMessage", chat_id=chat_id, message_id=wait_id)
            except: pass
        for f in [p, a, v]:
            if os.path.exists(f): os.remove(f)

async def bg_translate(chat_id, text):
    try:
        if not ai_client:
            await tg_send(chat_id, "❌ AI sozlanmagan (GEMINI_KEY yo'q).")
            return
        response = ai_client.models.generate_content(
            model="gemini-1.5-flash",
            contents=f"Siz professional tarjimon va tilshunosiz. Ushbu matnni tarjima qiling va qisqacha izoh bering: {text}"
        )
        await tg_send(chat_id, response.text)
    except Exception as e:
        await tg_send(chat_id, f"❌ AI xatolik: {e}")

# --- 9. WEBHOOK HANDLER ---
@app.post("/webhook/bot")
async def webhook_handler(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
    except:
        return JSONResponse({"ok": True})

    if "message" not in data:
        return JSONResponse({"ok": True})

    msg = data["message"]
    chat_id = msg["chat"]["id"]
    user_id = str(msg["from"]["id"])
    first_name = msg["from"].get("first_name", "Foydalanuvchi")
    text = msg.get("text", "")
    photo = msg.get("photo")
    audio = msg.get("audio") or msg.get("voice")
    video = msg.get("video")

    state, state_data = get_state(user_id)
    print(f"[*] from={user_id} state={state} text={text[:30] if text else ''}")

    # /start
    if text == "/start":
        set_state(user_id, None)
        try: db.add_user(user_id, first_name)
        except: pass
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": f"Xush kelibsiz, {first_name}! 🚀 Sadoon AI botiga xush kelibsiz.",
            "reply_markup": MAIN_KB
        })

    # 💎 Balans
    if text == "💎 Balans":
        balance = db.get_balance(user_id)
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": f"💎 Balansingiz: {balance} somoniy.\n🆔 ID: `{user_id}`",
            "parse_mode": "Markdown"
        })

    # 💰 To'ldirish
    if text == "💰 To'ldirish":
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": f"💰 To'ldirish uchun admin bilan bog'laning:\n👤 @husanjon007\n🆔 Sizning ID: `{user_id}`",
            "parse_mode": "Markdown"
        })

    # 📥 Yuklab olish
    if text == "📥 Yuklab olish":
        set_state(user_id, "waiting_download")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "🔗 Instagram, TikTok yoki YouTube havolasini yuboring."
        })

    # 🔍 Shazam
    if text == "🔍 Shazam":
        set_state(user_id, "waiting_shazam")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "🎧 Audio, ovozli xabar yoki video yuboring."
        })

    # 🎬 Klip Yaratish
    if text == "🎬 Klip Yaratish (V3) (🖼️ rasm + 🎵 musiqa)":
        set_state(user_id, "waiting_clip_photo")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "🖼️ Rasm yuboring."
        })

    # ✍️ Takliflar
    if text == "✍️ Takliflar":
        set_state(user_id, "waiting_feedback")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "✍️ Taklifingizni yozing."
        })

    # --- STATE HANDLERS ---

    if state == "waiting_download" and text:
        import re
        urls = re.findall(r'https?://[^\s]+', text)
        if urls:
            set_state(user_id, None)
            url = urls[0].strip('.,()!?')
            filename = f"v_{uuid.uuid4()}.mp4"
            output = f"output/{filename}"
            try:
                success = await asyncio.wait_for(
                    mixer.download_video(url, output), timeout=55
                )
                if success:
                    file_url = f"{BASE_URL}/output/{filename}"
                    background_tasks.add_task(_cleanup_file, output, 120)
                    return JSONResponse({
                        "method": "sendVideo",
                        "chat_id": chat_id,
                        "video": file_url,
                        "supports_streaming": True
                    })
                if os.path.exists(output): os.remove(output)
                return JSONResponse({
                    "method": "sendMessage", "chat_id": chat_id,
                    "text": "❌ Yuklab bo'lmadi. TikTok yoki YouTube havolasini sinab ko'ring."
                })
            except asyncio.TimeoutError:
                if os.path.exists(output): os.remove(output)
                return JSONResponse({
                    "method": "sendMessage", "chat_id": chat_id,
                    "text": "⏰ 55 soniya ichida yuklanmadi. Video juda katta yoki sayt bloklanган."
                })
            except Exception as e:
                if os.path.exists(output): os.remove(output)
                return JSONResponse({
                    "method": "sendMessage", "chat_id": chat_id,
                    "text": f"❌ Xatolik: {str(e)[:200]}"
                })
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "❌ Havola topilmadi. Iltimos, to'g'ri URL yuboring."
        })

    if state == "waiting_shazam" and (audio or video):
        file_id = audio["file_id"] if audio else video["file_id"]
        set_state(user_id, None)
        background_tasks.add_task(bg_shazam, chat_id, file_id)
        return JSONResponse({"ok": True})

    if state == "waiting_clip_photo" and photo:
        photo_id = photo[-1]["file_id"]
        set_state(user_id, "waiting_clip_audio", photo_id)
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "🎵 Endi audio (musiqa) yuboring."
        })

    if state == "waiting_clip_audio" and audio:
        audio_id = audio["file_id"]
        photo_id = state_data
        set_state(user_id, None)
        background_tasks.add_task(bg_clip, chat_id, photo_id, audio_id)
        return JSONResponse({"ok": True})

    if state == "waiting_feedback" and text:
        set_state(user_id, None)
        background_tasks.add_task(
            tg_send, int(ADMIN_ID),
            f"📩 Taklif:\n👤 {first_name} (ID: {user_id})\n\n{text}"
        )
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "✅ Taklifingiz adminga yuborildi. Rahmat!"
        })

    # Default
    return JSONResponse({
        "method": "sendMessage", "chat_id": chat_id,
        "text": "Asosiy menyu:", "reply_markup": MAIN_KB
    })

# --- 10. API ENDPOINTS ---
@app.get("/")
async def read_root():
    return {
        "status": "Sadoon API + Bot (A-Z Healthy)",
        "gemini": bool(ai_client),
        "bot_token": bool(BOT_TOKEN),
        "tg_api": TG_API[:40] + "..." if BOT_TOKEN else "NOT SET"
    }

@app.get("/debug/state/{user_id}")
async def debug_state(user_id: str):
    state, data = get_state(user_id)
    return {"user_id": user_id, "state": state, "data": data}

@app.post("/api/download-video")
async def api_download_video(request: Request,
                              x_api_key: Optional[str] = Header(None)):
    if SADOON_API_KEY and x_api_key != SADOON_API_KEY:
        raise HTTPException(403)
    url = request.query_params.get("url")
    if url is None:
        try:
            data = await request.json()
            url = data.get("url")
        except: pass
    if not url:
        return {"status": "error", "message": "URL missing"}
    uid = str(uuid.uuid4())[:8]
    output_file = f"output/vid_{uid}.mp4"
    try:
        if await mixer.download_video(url, output_file):
            return {"status": "success", "download_url": f"{BASE_URL}/output/vid_{uid}.mp4"}
        return {"status": "error", "message": "Download failed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
