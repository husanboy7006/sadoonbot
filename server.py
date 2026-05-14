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
from openai import AsyncOpenAI
from smm_prompts import post as smm_post, reels as smm_reels, plan as smm_plan
from smm_prompts import hashtag as smm_hashtag, caption as smm_caption, strategy as smm_strategy
import sqlite3

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

app.add_middleware(CORSMiddleware, allow_origins=["https://huggingface.co"], allow_credentials=True,
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
    print(f"[*] Gemini key loaded: ...{GEMINI_KEY[-6:]}")
else:
    print("[!] GEMINI_KEY topilmadi!")

# --- 5b. GROQ ---
GROQ_KEY = os.getenv("GROQ_KEY")
groq_client = None
if GROQ_KEY:
    try:
        from groq import AsyncGroq
        groq_client = AsyncGroq(api_key=GROQ_KEY)
        print(f"[*] Groq key loaded: ...{GROQ_KEY[-6:]}")
    except ImportError:
        print("[!] groq paketi o'rnatilmagan!")
else:
    print("[!] GROQ_KEY topilmadi!")

# --- 5c. REPLICATE ---
REPLICATE_KEY = os.getenv("REPLICATE_KEY")
if REPLICATE_KEY:
    os.environ["REPLICATE_API_TOKEN"] = REPLICATE_KEY
    print(f"[*] Replicate key loaded: ...{REPLICATE_KEY[-6:]}")
else:
    print("[!] REPLICATE_KEY topilmadi!")

# --- 5d. OPENAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = None
if OPENAI_API_KEY:
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    print(f"[*] OpenAI key loaded: ...{OPENAI_API_KEY[-6:]}")
else:
    print("[!] OPENAI_API_KEY topilmadi!")

SMM_PROMPTS = {
    "smm_post": smm_post.SYSTEM_PROMPT,
    "smm_reels": smm_reels.SYSTEM_PROMPT,
    "smm_plan": smm_plan.SYSTEM_PROMPT,
    "smm_hashtag": smm_hashtag.SYSTEM_PROMPT,
    "smm_caption": smm_caption.SYSTEM_PROMPT,
    "smm_strategy": smm_strategy.SYSTEM_PROMPT,
}

# --- 6. KEYBOARD ---
MAIN_KB = {
    "keyboard": [
        [{"text": "🎬 Klip Yaratish (V3) (🖼️ rasm + 🎵 musiqa)"}],
        [{"text": "🚀 CGI Product Artist (Premium v2)"}],
        [{"text": "📥 Yuklab olish"}, {"text": "🔍 Shazam"}],
        [{"text": "🌐 Tilmoch AI"}, {"text": "💎 Balans"}],
        [{"text": "✍️ SMM Studio"}],
        [{"text": "✍️ Takliflar"}, {"text": "💰 To'ldirish"}]
    ],
    "resize_keyboard": True
}

SMM_KB = {
    "keyboard": [
        [{"text": "📝 Post yozish"}, {"text": "🎬 Reels ssenariy"}],
        [{"text": "📅 Kontent plan"}, {"text": "#️⃣ Hashtag"}],
        [{"text": "💬 Caption"}, {"text": "📊 Strategiya"}],
        [{"text": "🔙 Orqaga"}]
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

async def bg_shazam(chat_id):
    await tg_send(chat_id, "❌ Shazam vaqtincha ishlamaydi.")

async def bg_smm(chat_id, user_id, text, mode):
    result = None
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SMM_PROMPTS[mode]},
                {"role": "user", "content": text},
            ],
            max_tokens=5000,
            temperature=0.8,
        )
        result = response.choices[0].message.content
    except Exception as e:
        logging.error(f"OpenAI xato: {e}")
    if result is None:
        await tg("sendMessage", chat_id=chat_id, text="❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.", reply_markup=SMM_KB)
    else:
        db.update_balance(user_id, -1)
        db.log_stats(user_id, mode)
        remaining = db.get_balance(user_id)
        if len(result) > 4000:
            for part in [result[i:i+4000] for i in range(0, len(result), 4000)]:
                await tg("sendMessage", chat_id=chat_id, text=part)
        else:
            await tg("sendMessage", chat_id=chat_id, text=result)
        await tg("sendMessage", chat_id=chat_id, text=f"📊 Qolgan balans: {remaining} ta", reply_markup=SMM_KB)

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

CGI_PROMPT = """You are a world-class CGI Product Visualization Director and advertising creative director.
TASK: Take this product and create a HIGH-END, cinematic advertising image.
- Professional studio lighting with dramatic shadows
- Luxury background matching the vibe
- Photorealistic render quality
- No text overlays
Vibe: {vibe}
Platform format: {plat}"""

async def bg_cgi(chat_id, photo_id, vibe, plat):
    import base64, replicate as repl
    p = f"temp/p_{uuid.uuid4()}.jpg"
    wait_id = None
    try:
        wait = await tg("sendMessage", chat_id=chat_id, text="⏳ CGI Artist ishlamoqda (30-60 soniya)...")
        wait_id = wait.get("result", {}).get("message_id")
        await tg_download(photo_id, p)
        with open(p, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        img_uri = f"data:image/jpeg;base64,{img_b64}"
        prompt = (
            f"Ultra-high-end CGI product photography, {vibe} style, "
            f"professional studio lighting with dramatic shadows, luxury background, "
            f"commercial advertising for {plat}, 8K resolution, photorealistic, "
            f"award-winning product shot, no text, no watermark"
        )
        output = await repl.async_run(
            "black-forest-labs/flux-dev",
            input={
                "prompt": prompt,
                "image": img_uri,
                "strength": 0.75,
                "num_inference_steps": 28,
                "guidance": 3.5,
                "output_format": "jpeg",
            }
        )
        img_url = str(output[0]) if output else None
        if img_url:
            await tg("sendPhoto", chat_id=chat_id, photo=img_url, caption=f"💎 CGI: {vibe} / {plat}")
        else:
            await tg_send(chat_id, "❌ Replicate rasm yarata olmadi.")
    except Exception as e:
        await tg_send(chat_id, f"❌ CGI xatolik: {str(e)[:200]}")
    finally:
        if wait_id:
            try: await tg("deleteMessage", chat_id=chat_id, message_id=wait_id)
            except: pass
        if os.path.exists(p): os.remove(p)

async def bg_translate(chat_id, text):
    try:
        if not ai_client:
            await tg_send(chat_id, "❌ AI sozlanmagan (GEMINI_KEY yo'q).")
            return
        response = await ai_client.aio.models.generate_content(
            model="gemini-2.0-flash-lite",
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

    # 🌐 Tilmoch AI
    if text == "🌐 Tilmoch AI":
        set_state(user_id, "waiting_translate")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "✍️ Tarjima qilinadigan matnni yuboring."
        })

    # 🚀 CGI
    if text == "🚀 CGI Product Artist (Premium v2)":
        set_state(user_id, "waiting_cgi_photo")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "📸 Reklama qilmoqchi bo'lgan mahsulotingiz rasmini yuboring."
        })

    # ✍️ Takliflar
    if text == "✍️ Takliflar":
        set_state(user_id, "waiting_feedback")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "✍️ Taklifingizni yozing."
        })

    # ✍️ SMM Studio
    if text == "✍️ SMM Studio":
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "✍️ <b>SMM Studio</b>\n\nQaysi xizmatdan foydalanmoqchisiz?",
            "parse_mode": "HTML", "reply_markup": SMM_KB
        })

    if text == "🔙 Orqaga":
        set_state(user_id, None)
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "Asosiy menyu:", "reply_markup": MAIN_KB
        })

    if text == "📝 Post yozish":
        set_state(user_id, "smm_post")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "📝 Qaysi mavzuda post yozay?\n\n<i>Misol: Go'zallik saloni uchun aktsiya posti</i>",
            "parse_mode": "HTML"
        })

    if text == "🎬 Reels ssenariy":
        set_state(user_id, "smm_reels")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "🎬 Qanday mavzuda reels ssenariy yozay?\n\n<i>Misol: Kafe uchun 'bir kunim' formatida reels</i>",
            "parse_mode": "HTML"
        })

    if text == "📅 Kontent plan":
        set_state(user_id, "smm_plan")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "📅 Qaysi nisha uchun 30 kunlik plan tuzay?\n\n<i>Misol: Online kiyim do'koni</i>",
            "parse_mode": "HTML"
        })

    if text == "#️⃣ Hashtag":
        set_state(user_id, "smm_hashtag")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "#️⃣ Qaysi mavzu uchun hashtag kerak?\n\n<i>Misol: Fitness va sport ozuqa</i>",
            "parse_mode": "HTML"
        })

    if text == "💬 Caption":
        set_state(user_id, "smm_caption")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "💬 Rasm tavsifi yoki mavzuni yozing:\n\n<i>Misol: Yangi kolleksiya keldi, stilist fotosessiya</i>",
            "parse_mode": "HTML"
        })

    if text == "📊 Strategiya":
        set_state(user_id, "smm_strategy")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "📊 Biznes turingiz va maqsadingizni yozing:\n\n<i>Misol: Stomatologiya klinikasi, Instagram orqali mijoz jalb qilish</i>",
            "parse_mode": "HTML"
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
                    db.log_stats(user_id, "download")
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

    if state == "waiting_translate" and text:
        set_state(user_id, None)
        result = None
        TILMOCH_SYSTEM = """Sen "Tilmoch AI" — O'zbek, Rus va Xitoy tillari o'rtasida professional darajadagi tezkor tarjimon.

Qoidalar:
- Hech qachon o'zingni tanishtirma, kirish gaplari yozma
- Foydalanuvchi nima yuborsa darhol tarjimaga o't, ortiqcha gap yozma
- Faqat tarjima bilan shug'ullan

Til aniqlash:
- O'zbek matni → Ruscha va Xitoycha tarjima qil
- Ruscha matn → O'zbekcha tarjima qil
- Xitoycha matn → O'zbekcha tarjima qil

Chiqish formati (qat'iy):
📝 Original: [asl matn]

🇺🇿 O'zbekcha: [tarjima]

🇷🇺 Ruscha:
```
[ruscha tarjima]
```

🇨🇳 Xitoycha:
```
[xitoycha tarjima]
```
🔤 Talaffuz: [pinyin ohanglar + o'zbekcha o'qilishi]

💬 Namuna javoblar:
1. [1-variant]
2. [2-variant]"""
        # 1. Groq bilan urinib ko'r (asosiy)
        if groq_client and not result:
            try:
                chat = await groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": TILMOCH_SYSTEM},
                        {"role": "user", "content": text}
                    ],
                    max_tokens=1500,
                    timeout=20
                )
                result = chat.choices[0].message.content[:4000]
            except Exception as e:
                print(f"[!] Tilmoch Groq xato: {e}")
        # 2. Gemini fallback
        if ai_client and not result:
            try:
                from google.genai import types as genai_types
                response = await asyncio.wait_for(
                    ai_client.aio.models.generate_content(
                        model="gemini-1.5-flash",
                        contents=text,
                        config=genai_types.GenerateContentConfig(
                            system_instruction=TILMOCH_SYSTEM,
                        )
                    ), timeout=20
                )
                result = response.text[:4000]
            except Exception as e:
                print(f"[!] Tilmoch Gemini xato: {e}")
        # 2. Fallback: MyMemory (bepul, kalitsiz)
        if not result:
            try:
                import urllib.parse
                q = urllib.parse.quote(text[:500])
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        f"https://api.mymemory.translated.net/get?q={q}&langpair=ru|uz",
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as r:
                        data = await r.json()
                        if data.get("responseStatus") == 200:
                            t = data["responseData"]["translatedText"]
                            result = f"🌐 Tarjima (O'zbekcha):\n{t}"
                        else:
                            print(f"[!] MyMemory xato: {data}")
            except Exception as e:
                print(f"[!] MyMemory fallback xato: {e}")
        if not result:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": "❌ Tarjima qilib bo'lmadi. Keyinroq urinib ko'ring."})
        return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": result})

    if state == "waiting_cgi_photo" and photo:
        photo_id = photo[-1]["file_id"]
        set_state(user_id, "waiting_cgi_choices", photo_id)
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "🎨 Vibe: 1-Luxury 2-Fresh 3-Dark 4-Minimal 5-Energetic\n📐 Platforma: 1-Instagram 2-Story 3-Banner 4-Poster\nMisol: 1 2"
        })

    if state == "waiting_cgi_choices" and text:
        choices = text.split()
        if len(choices) < 2:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": "Iltimos, ikkita raqam yuboring: masalan 1 2"})
        vibe_map = {"1": "Luxury", "2": "Fresh", "3": "Dark", "4": "Minimal", "5": "Energetic"}
        plat_map = {"1": "Instagram", "2": "Story", "3": "Banner", "4": "Poster"}
        vibe = vibe_map.get(choices[0], "Luxury")
        plat = plat_map.get(choices[1], "Instagram")
        photo_id = state_data
        set_state(user_id, None)
        if not REPLICATE_KEY:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": "❌ REPLICATE_KEY sozlanmagan."})
        background_tasks.add_task(bg_cgi, chat_id, photo_id, vibe, plat)
        return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": "⏳ CGI Artist ishlamoqda (30-60 soniya)..."})

    if state == "waiting_shazam" and (audio or video):
        set_state(user_id, None)
        background_tasks.add_task(bg_shazam, chat_id)
        return JSONResponse({"ok": True})

    if state == "waiting_clip_photo" and photo:
        photo_id = photo[-1]["file_id"]
        set_state(user_id, "waiting_clip_audio", photo_id)
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "🎵 Endi audio (musiqa) yuboring."
        })

    if state == "waiting_clip_audio":
        photo_id = state_data
        set_state(user_id, None)
        p = f"temp/p_{uuid.uuid4()}.jpg"
        a = f"temp/a_{uuid.uuid4()}.mp3"
        v = f"output/v_{uuid.uuid4()}.mp4"
        try:
            await tg_download(photo_id, p)
            if audio:
                await tg_download(audio["file_id"], a)
            elif text:
                import re
                urls = re.findall(r'https?://[^\s]+', text)
                if not urls:
                    return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": "❌ Audio fayl yoki havola yuboring."})
                ok = await asyncio.wait_for(mixer.download_audio(urls[0].strip('.,()!?'), a), timeout=55)
                if not ok:
                    return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": "❌ Musiqa yuklab bo'lmadi."})
            else:
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": "❌ Audio fayl yoki havola yuboring."})
            if not await mixer.mix_image_audio(p, a, v):
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": "❌ Klip yaratishda xatolik."})
            file_url = f"{BASE_URL}/output/{os.path.basename(v)}"
            background_tasks.add_task(_cleanup_file, v, 300)
            db.log_stats(user_id, "mix")
            return JSONResponse({"method": "sendVideo", "chat_id": chat_id, "video": file_url, "supports_streaming": True})
        except asyncio.TimeoutError:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": "⏰ Vaqt tugadi. Qisqaroq video sinab ko'ring."})
        except Exception as e:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": f"❌ Xato: {str(e)[:200]}"})
        finally:
            for f in [p, a]:
                if os.path.exists(f): os.remove(f)

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

    if state in ("smm_post", "smm_reels", "smm_plan", "smm_hashtag", "smm_caption", "smm_strategy") and text:
        balance = db.get_balance(user_id)
        if balance <= 0:
            set_state(user_id, None)
            return JSONResponse({
                "method": "sendMessage", "chat_id": chat_id,
                "text": "⚠️ Balansingiz tugagan!\n\n💰 To'ldirish uchun /start bosing va To'ldirish tugmasini tanlang.",
                "reply_markup": MAIN_KB
            })
        if not openai_client:
            set_state(user_id, None)
            return JSONResponse({
                "method": "sendMessage", "chat_id": chat_id,
                "text": "❌ OpenAI API kalit sozlanmagan.", "reply_markup": SMM_KB
            })
        mode = state
        set_state(user_id, None)
        background_tasks.add_task(bg_smm, chat_id, user_id, text, mode)
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "⏳ SMM AI ishlamoqda..."
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
async def debug_state(user_id: str, x_api_key: Optional[str] = Header(None)):
    if SADOON_API_KEY and x_api_key != SADOON_API_KEY:
        raise HTTPException(403, detail="Forbidden")
    if not SADOON_API_KEY and str(user_id) != str(ADMIN_ID):
        raise HTTPException(403, detail="Forbidden")
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

async def _register_webhook():
    await asyncio.sleep(5)
    if not BOT_TOKEN or BASE_URL == "http://localhost:7860":
        print(f"[!] Webhook o'rnatilmadi. BASE_URL={BASE_URL}")
        return
    webhook_url = f"{BASE_URL}/webhook/bot"
    for attempt in range(5):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(f"{TG_API}/setWebhook", json={"url": webhook_url, "drop_pending_updates": True}) as r:
                    result = await r.json()
                    print(f"[*] Webhook: {webhook_url} -> {result.get('description', result)}")
                    return
        except Exception as e:
            print(f"[!] Webhook attempt {attempt+1} failed: {e}")
            if attempt < 4:
                await asyncio.sleep(10)
    print("[!] Webhook ro'yxatdan o'tmadi!")

@app.on_event("startup")
async def on_startup():
    global BASE_URL
    railway_host = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    space_host = os.getenv("SPACE_HOST")
    if railway_host:
        BASE_URL = f"https://{railway_host}"
    elif space_host:
        BASE_URL = f"https://{space_host}"
    asyncio.create_task(_register_webhook())

if __name__ == "__main__":
    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
