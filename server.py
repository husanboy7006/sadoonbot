import os
import re
import json
import uuid
import asyncio
import logging
import socket
import aiohttp
from typing import Optional
# --- 1. DNS PATCH ---
def apply_dns_patch():
    try:
        old_getaddrinfo = socket.getaddrinfo
        def new_getaddrinfo(*args, **kwargs):
            try:
                return old_getaddrinfo(*args, **kwargs)
            except socket.gaierror as e:
                print(f"[!] DNS xatosi: {args[0]} — {e}")
                raise
        socket.getaddrinfo = new_getaddrinfo
        print("[*] DNS Patch applied.")
    except Exception as e:
        print(f"[!] DNS Patch failed: {e}")

apply_dns_patch()

# --- 2. FASTAPI ---
from contextlib import asynccontextmanager
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
logging.basicConfig(filename='server.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

@asynccontextmanager
async def lifespan(_app: FastAPI):
    global BASE_URL
    railway_host = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    space_host = os.getenv("SPACE_HOST")
    if railway_host:
        BASE_URL = f"https://{railway_host}"
    elif space_host:
        BASE_URL = f"https://{space_host}"
    asyncio.create_task(_register_webhook())
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
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

SMM_FREE_DAILY = int(os.getenv("FREE_DAILY_LIMIT", "3"))
SMM_PREMIUM_DAILY = int(os.getenv("PREMIUM_DAILY_LIMIT", "30"))
SMM_MAX_TOKENS = int(os.getenv("MAX_TOKENS", "5000"))
SMM_TEMPERATURE = float(os.getenv("TEMPERATURE", "0.8"))
PAYMENT_ADMIN = os.getenv("PAYMENT_ADMIN", "@husanjon007")

TILMOCH_SYSTEM = """Sen "Tilmoch AI" — O'zbek, Rus va Xitoy tillari o'rtasida tezkor va aniq tarjimon.

Qoidalar:
- Kirish gaplari yozma, darhol tarjimaga o't
- Bitta so'z bo'lsa ham tarjima qil
- Ortiqcha tushuntirma berma

Til aniqlash (qat'iy):
- Latin yoki o'zbek harflari (a, b, o', g', sh, ch...) → O'ZBEK tili → Ruscha VA Xitoycha tarjima qil
- Kirill harflar (а, б, в, г...) yoki rus so'zlari → RUS tili → faqat O'zbekcha tarjima qil
- Xitoy ierogliflari → XiTOY tili → faqat O'zbekcha tarjima qil

Chiqish formati (qat'iy, o'zgartirma):

O'zbek matni uchun:
📝 Original: [asl matn]
🇷🇺 Ruscha: [ruscha tarjima]
🇨🇳 Xitoycha: [xitoycha tarjima]
🔤 Talaffuz: [pinyin + o'zbekcha o'qilishi]

Rus matni uchun:
📝 Original: [asl matn]
🇺🇿 O'zbekcha: [o'zbekcha tarjima]

Xitoy matni uchun:
📝 Original: [asl matn]
🇺🇿 O'zbekcha: [o'zbekcha tarjima]
🔤 Talaffuz: [pinyin + o'zbekcha o'qilishi]"""
PLAN_INFO = {
    "starter": {"name": "⭐ Plus", "price": "29,000 so'm", "days": 30},
}
pending_payments: dict = {}

# --- 6. KEYBOARD ---
MAIN_KB = {
    "keyboard": [
        [{"text": "🆓 Bepul xizmatlar"}],
        [{"text": "💎 Pullik xizmatlar"}],
        [{"text": "✍️ Takliflar"}]
    ],
    "resize_keyboard": True
}

FREE_KB = {
    "keyboard": [
        [{"text": "📥 Yuklab olish"}, {"text": "🌐 Tilmoch AI"}],
        [{"text": "🤖 AI Suhbat"}, {"text": "🧮 Kalkulator"}],
        [{"text": "🎬 Klip Yaratish"}],
        [{"text": "🔍 Shazam"}],
        [{"text": "🔙 Orqaga"}]
    ],
    "resize_keyboard": True
}

PAID_KB = {
    "keyboard": [
        [{"text": "✍️ SMM Studio"}],
        [{"text": "💎 Plus olish"}, {"text": "📊 Mening limitim"}],
        [{"text": "🔙 Orqaga"}]
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

# --- 6b. CALCULATOR ---
from calc_parser import safe_calc, format_result, CalcError

_calc_expr: dict = {}
_calc_history: dict = {}
_calc_awaiting: dict = {}

def _cb(t, d): return {"text": t, "callback_data": d}

def _calc_kb(mode="basic"):
    if mode == "science":
        rows = [
            [_cb("sin","c_sin("),_cb("cos","c_cos("),_cb("tan","c_tan("),_cb("⌫","c_back")],
            [_cb("log","c_log("),_cb("ln","c_ln("),_cb("√","c_sqrt("),_cb("x²","c_^2")],
            [_cb("π","c_π"),_cb("e","c_e"),_cb("(","c_("),_cb(")","c_)")],
            [_cb("xⁿ","c_^"),_cb("1/x","c_1/x"),_cb("n!","c_!"),_cb("C","c_C")],
            [_cb("7","c_7"),_cb("8","c_8"),_cb("9","c_9"),_cb("÷","c_÷")],
            [_cb("4","c_4"),_cb("5","c_5"),_cb("6","c_6"),_cb("×","c_×")],
            [_cb("1","c_1"),_cb("2","c_2"),_cb("3","c_3"),_cb("−","c_−")],
            [_cb("🔢","c_mode_basic"),_cb("0","c_0"),_cb(".","c_."),_cb("=","c_=")],
        ]
    else:
        rows = [
            [_cb("C","c_C"),_cb("⌫","c_back"),_cb("%","c_%"),_cb("÷","c_÷")],
            [_cb("7","c_7"),_cb("8","c_8"),_cb("9","c_9"),_cb("×","c_×")],
            [_cb("4","c_4"),_cb("5","c_5"),_cb("6","c_6"),_cb("−","c_−")],
            [_cb("1","c_1"),_cb("2","c_2"),_cb("3","c_3"),_cb("+","c_+")],
            [_cb("🔬 Ilmiy","c_mode_science"),_cb("0","c_0"),_cb(".","c_."),_cb("=","c_=")],
            [_cb("(","c_("),_cb(")","c_)"),_cb("📜","c_history"),_cb("🏠","c_menu")],
        ]
    return {"inline_keyboard": rows}

def _calc_menu_kb():
    return {"inline_keyboard": [
        [_cb("🔢 Kalkulator","c_mode_basic"),_cb("🔬 Ilmiy","c_mode_science")],
        [_cb("💱 Valyuta","c_open_currency"),_cb("📏 Birliklar","c_open_convert")],
        [_cb("📜 Tarix","c_history")],
    ]}

def _calc_result_kb():
    return {"inline_keyboard": [
        [_cb("🔢 Yana hisoblash","c_mode_basic"),_cb("📜 Tarix","c_history")],
        [_cb("💱 Valyuta","c_open_currency"),_cb("📏 Birliklar","c_open_convert")],
        [_cb("🏠 Bosh menyu","c_menu")],
    ]}

def _calc_history_kb():
    return {"inline_keyboard": [
        [_cb("🗑 Tarixni tozalash","c_clear_history"),_cb("🔢 Kalkulator","c_mode_basic")],
        [_cb("🏠 Bosh menyu","c_menu")],
    ]}

def _calc_currency_kb():
    return {"inline_keyboard": [
        [_cb("🇺🇸 USD → UZS","c_cur_USD_UZS"),_cb("🇺🇿 UZS → USD","c_cur_UZS_USD")],
        [_cb("🇪🇺 EUR → UZS","c_cur_EUR_UZS"),_cb("🇷🇺 RUB → UZS","c_cur_RUB_UZS")],
        [_cb("🏠 Bosh menyu","c_menu")],
    ]}

def _calc_convert_kb():
    return {"inline_keyboard": [
        [_cb("km ↔ mi","c_conv_km_mi"),_cb("kg ↔ lb","c_conv_kg_lb")],
        [_cb("°C ↔ °F","c_conv_c_f"),_cb("m ↔ ft","c_conv_m_ft")],
        [_cb("🏠 Bosh menyu","c_menu")],
    ]}

async def _get_rates():
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/",
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
                return {item["Ccy"]: float(item["Rate"]) for item in data}
    except: return {}

async def _convert_currency(amount, from_cur, to_cur):
    rates = await _get_rates()
    if not rates: raise Exception("CBU serveriga ulanib bo'lmadi")
    if from_cur == "UZS":
        return amount / rates[to_cur]
    elif to_cur == "UZS":
        return amount * rates[from_cur]
    return amount * rates[from_cur] / rates[to_cur]

def _convert_unit(amount, conv_type):
    c = {
        "km_mi":(lambda x:x*0.621371,lambda x:x/0.621371,"km","mi"),
        "kg_lb":(lambda x:x*2.20462,lambda x:x/2.20462,"kg","lb"),
        "c_f":(lambda x:x*9/5+32,lambda x:(x-32)*5/9,"°C","°F"),
        "m_ft":(lambda x:x*3.28084,lambda x:x/3.28084,"m","ft"),
    }
    if conv_type not in c: raise ValueError("Noma'lum tur")
    fwd,bwd,u1,u2 = c[conv_type]
    return (f"📏 <b>Birlik o'zgartirish</b>\n\n"
            f"<code>{amount:,.2f} {u1}</code> = <b>{fwd(amount):,.4f} {u2}</b>\n"
            f"<code>{amount:,.2f} {u2}</code> = <b>{bwd(amount):,.4f} {u1}</b>")

# --- 7. TELEGRAM HELPERS ---
_TG_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=15)

def fmt_date(date_str):
    try:
        from datetime import datetime
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    except:
        return date_str

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

async def tg_download(file_id, save_path):
    try:
        async with aiohttp.ClientSession(timeout=_TG_TIMEOUT) as s:
            async with s.get(f"{TG_API}/getFile?file_id={file_id}") as r:
                info = await r.json()
            fp = (info.get("result") or {}).get("file_path")
            if not fp:
                raise ValueError(f"file_path topilmadi: {info}")
            async with s.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{fp}") as r:
                with open(save_path, "wb") as f:
                    f.write(await r.read())
    except Exception as e:
        print(f"[TG] tg_download xatosi: {e}")
        raise

# --- 8. BACKGROUND TASKS ---
async def _cleanup_file(path, delay=60):
    await asyncio.sleep(delay)
    try:
        if os.path.exists(path): os.remove(path)
    except: pass

async def bg_shazam_url(chat_id, user_id, url, audio_path):
    tmp_v = audio_path + ".tmp.mp4"
    try:
        # 1. Avval video yuklab, audio ajratamiz
        downloaded = await asyncio.wait_for(
            mixer.download_video(url, tmp_v), timeout=50
        )
        if downloaded and os.path.exists(tmp_v) and os.path.getsize(tmp_v) > 1000:
            ok = await mixer.extract_audio_from_video(tmp_v, audio_path)
            if os.path.exists(tmp_v): os.remove(tmp_v)
            if ok:
                await bg_shazam(chat_id, audio_path)
                return
        if os.path.exists(tmp_v): os.remove(tmp_v)
        await tg_send(chat_id, "❌ Audio yuklab bo'lmadi. Audio fayl yoki boshqa havola yuboring.")
    except asyncio.TimeoutError:
        for f in [tmp_v, audio_path]:
            if os.path.exists(f): os.remove(f)
        await tg_send(chat_id, "⏰ Yuklab bo'lmadi. Boshqa havola sinab ko'ring.")
    except Exception as e:
        for f in [tmp_v, audio_path]:
            if os.path.exists(f): os.remove(f)
        await tg_send(chat_id, f"❌ Xatolik: {str(e)[:200]}")

async def bg_shazam(chat_id, audio_path):
    try:
        result = await asyncio.wait_for(mixer.identify_music(audio_path), timeout=30)
        if result:
            text = (
                f"🎵 <b>{result['title']}</b>\n"
                f"🎤 {result['artist']}\n"
            )
            if result.get("album"):
                text += f"💿 {result['album']}\n"
            if result.get("url"):
                text += f"\n🔗 <a href='{result['url']}'>Shazam da ochish</a>"
            await tg("sendMessage", chat_id=chat_id, text=text,
                     parse_mode="HTML", disable_web_page_preview=False)
        else:
            await tg_send(chat_id, "❌ Qo'shiq aniqlanmadi. Boshqa audio sinab ko'ring.")
    except asyncio.TimeoutError:
        await tg_send(chat_id, "⏰ Vaqt tugadi. Qaytadan urinib ko'ring.")
    except Exception as e:
        await tg_send(chat_id, f"❌ Xatolik: {str(e)[:200]}")
    finally:
        if os.path.exists(audio_path): os.remove(audio_path)

async def bg_mix_clip(chat_id, user_id, p, a, v):
    try:
        await mixer.mix_image_audio(p, a, v)
        file_url = f"{BASE_URL}/output/{os.path.basename(v)}"
        asyncio.create_task(_cleanup_file(v, 300))
        db.log_stats(user_id, "mix")
        await tg("sendVideo", chat_id=chat_id, video=file_url, supports_streaming=True)
    except Exception as e:
        await tg_send(chat_id, f"❌ Klip yaratishda xatolik: {str(e)[:200]}")
    finally:
        for f in [p, a]:
            if os.path.exists(f): os.remove(f)

async def bg_download(chat_id, user_id, url):
    filename = f"v_{uuid.uuid4()}.mp4"
    output = f"output/{filename}"
    try:
        success = await asyncio.wait_for(
            mixer.download_video(url, output), timeout=55
        )
        if not success or not os.path.exists(output) or os.path.getsize(output) < 1000:
            if os.path.exists(output): os.remove(output)
            await tg_send(chat_id, "❌ Yuklab bo'lmadi. TikTok yoki YouTube havolasini sinab ko'ring.")
            return

        file_size = os.path.getsize(output)
        print(f"[+] Video yuklandi: {output} ({file_size // 1024} KB)")

        # 50MB dan katta bo'lsa siqamiz
        if file_size > 50 * 1024 * 1024:
            await tg_send(chat_id, "📦 Video katta, siqilmoqda...")
            compressed = output.replace(".mp4", "_c.mp4")
            ok = await mixer.compress_video(output, compressed)
            if os.path.exists(output): os.remove(output)
            if ok and os.path.exists(compressed):
                output = compressed
                filename = os.path.basename(compressed)
                file_size = os.path.getsize(compressed)
                print(f"[+] Siqildi: {compressed} ({file_size // 1024} KB)")
            else:
                if os.path.exists(compressed): os.remove(compressed)
                await tg_send(chat_id, "❌ Video juda katta va siqib bo'lmadi. Qisqaroq video sinab ko'ring.")
                return

        file_url = f"{BASE_URL}/output/{filename}"
        db.log_stats(user_id, "download")

        # Telegram ga yuborish — URL orqali
        resp = await tg("sendVideo", chat_id=chat_id, video=file_url, supports_streaming=True,
                 caption="🤖 <b>Sadoon AI</b> — video yuklab olish, tarjimon, SMM va boshqa xizmatlar!\n👉 @sadoon_ai_bot",
                 parse_mode="HTML")

        if not resp.get("ok"):
            print(f"[!] sendVideo failed: {resp}")
            # URL orqali bo'lmasa, fayl sifatida yuboramiz
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
                with open(output, "rb") as f:
                    form = aiohttp.FormData()
                    form.add_field("chat_id", str(chat_id))
                    form.add_field("supports_streaming", "true")
                    form.add_field("caption", "🤖 <b>Sadoon AI</b> — video yuklab olish, tarjimon, SMM va boshqa xizmatlar!\n👉 @sadoon_ai_bot")
                    form.add_field("parse_mode", "HTML")
                    form.add_field("video", f, filename=filename, content_type="video/mp4")
                    async with s.post(f"{TG_API}/sendVideo", data=form) as r:
                        resp2 = await r.json()
                        if not resp2.get("ok"):
                            print(f"[!] sendVideo (file) failed: {resp2}")
                            await tg_send(chat_id, f"❌ Video yuborishda xatolik: {resp2.get('description', '')}")

        asyncio.create_task(_cleanup_file(output, 120))
    except (asyncio.TimeoutError, asyncio.CancelledError):
        if os.path.exists(output): os.remove(output)
        await tg_send(chat_id, "⏰ 55 soniya ichida yuklanmadi. Video juda katta yoki sayt bloklangan.")
    except Exception as e:
        if os.path.exists(output): os.remove(output)
        await tg_send(chat_id, f"❌ Xatolik: {str(e)[:200]}")

async def bg_broadcast(admin_chat_id, msg: dict):
    users = db.get_all_users()
    total = len(users)
    sent = 0
    failed = 0
    photo = msg.get("photo")
    video = msg.get("video")
    caption = msg.get("caption", "")
    text_msg = msg.get("text", "")
    for user_id in users:
        try:
            if photo:
                await tg("sendPhoto", chat_id=int(user_id),
                         photo=photo[-1]["file_id"], caption=caption, parse_mode="HTML")
            elif video:
                await tg("sendVideo", chat_id=int(user_id),
                         video=video["file_id"], caption=caption, parse_mode="HTML")
            else:
                await tg("sendMessage", chat_id=int(user_id),
                         text=text_msg, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await tg("sendMessage", chat_id=admin_chat_id,
             text=f"✅ <b>Reklama yuborildi!</b>\n\n👥 Jami: {total} ta\n✅ Yuborildi: {sent} ta\n❌ Bloklanган: {failed} ta",
             parse_mode="HTML")

async def bg_smm(chat_id, user_id, text, mode):
    allowed, used, daily_limit, is_prem = db.try_smm(user_id, SMM_FREE_DAILY, SMM_PREMIUM_DAILY)
    if not allowed:
        keyboard = {"inline_keyboard": [
            [{"text": "⭐ Plus — 29,000 so'm/oy", "callback_data": "pay_starter"}],
        ]}
        await tg("sendMessage", chat_id=chat_id, text=(
            f"⚠️ <b>Kunlik limit tugadi!</b>\n\n"
            f"📝 Bugun {used}/{daily_limit} ta so'rov ishlatildi.\n\n"
            f"💎 Ko'proq ishlash uchun Plus oling:"
        ), parse_mode="HTML", reply_markup=keyboard)
        return
    result = None
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SMM_PROMPTS[mode]},
                {"role": "user", "content": text},
            ],
            max_tokens=SMM_MAX_TOKENS,
            temperature=SMM_TEMPERATURE,
        )
        result = response.choices[0].message.content
    except Exception as e:
        logging.error(f"OpenAI xato: {e}")
    if result is None:
        await tg("sendMessage", chat_id=chat_id, text="❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.", reply_markup=SMM_KB)
    else:
        db.log_stats(user_id, mode)
        if len(result) > 4000:
            for part in [result[i:i+4000] for i in range(0, len(result), 4000)]:
                await tg("sendMessage", chat_id=chat_id, text=part)
        else:
            await tg("sendMessage", chat_id=chat_id, text=result)
        remaining = max(0, daily_limit - used)
        if is_prem:
            footer = f"💎 Plus: {remaining}/{daily_limit} ta so'rov qoldi"
        else:
            footer = f"📊 Qolgan bepul so'rovlar: {remaining}/{daily_limit}"
        await tg("sendMessage", chat_id=chat_id, text=footer, reply_markup=SMM_KB)

# --- 9. WEBHOOK HANDLER ---
async def handle_callback_query(query: dict):
    cq_id = query["id"]
    data = query.get("data", "")
    from_id = query["from"]["id"]
    chat_id = query["message"]["chat"]["id"]
    msg_id = query["message"]["message_id"]

    # Tarif tanlash — foydalanuvchi
    if data.startswith("pay_"):
        await tg("answerCallbackQuery", callback_query_id=cq_id)
        plan = data.replace("pay_", "")
        if plan not in PLAN_INFO:
            return JSONResponse({"ok": True})
        info = PLAN_INFO[plan]
        db.set_state(str(from_id), f"waiting_payment_{plan}")
        await tg("sendMessage", chat_id=chat_id, text=(
            f"💰 <b>To'lov ko'rsatmasi</b>\n\n"
            f"📌 Tarif: {info['name']}\n"
            f"💵 Narx: {info['price']}\n"
            f"📅 Muddat: {info['days']} kun\n\n"
            f"1️⃣ {PAYMENT_ADMIN} ga yozing\n"
            f"2️⃣ Tarif nomini ayting: <b>{info['name']}</b>\n"
            f"3️⃣ To'lovni amalga oshiring\n"
            f"4️⃣ To'lov chekini (screenshot) <b>shu botga</b> yuboring\n\n"
            f"⏳ Admin tekshirib, plus faollashtiriladi.\n"
            f"❌ Bekor qilish: /start"
        ), parse_mode="HTML")
        return JSONResponse({"ok": True})

    # Admin tasdiqlash
    if data.startswith("approve_"):
        if from_id != ADMIN_ID:
            await tg("answerCallbackQuery", callback_query_id=cq_id, text="⛔ Ruxsat yo'q.", show_alert=True)
            return JSONResponse({"ok": True})
        await tg("answerCallbackQuery", callback_query_id=cq_id)
        _, uid, days = data.split("_")
        uid, days = int(uid), int(days)
        until = db.activate_premium(str(uid), days)
        old_caption = query["message"].get("caption", "")
        await tg("editMessageCaption", chat_id=chat_id, message_id=msg_id,
                 caption=old_caption + f"\n\n✅ Tasdiqlandi! {fmt_date(until)} gacha", parse_mode="HTML")
        _, sdata = db.get_state(str(uid))
        user_chat = None
        if sdata:
            try: user_chat = json.loads(sdata).get("chat_id")
            except: pass
        if not user_chat and uid in pending_payments:
            user_chat = pending_payments.pop(uid)["chat_id"]
        if user_chat:
            await tg("sendMessage", chat_id=user_chat, text=(
                f"🎉 <b>Plus faollashtirildi!</b>\n\n"
                f"📅 {fmt_date(until)} gacha amal qiladi\n"
                f"✅ Kuniga {SMM_PREMIUM_DAILY} ta SMM so'rovdan foydalaning!\n\n/start"
            ), parse_mode="HTML")
        return JSONResponse({"ok": True})

    # Admin rad etish
    if data.startswith("reject_"):
        if from_id != ADMIN_ID:
            await tg("answerCallbackQuery", callback_query_id=cq_id, text="⛔ Ruxsat yo'q.", show_alert=True)
            return JSONResponse({"ok": True})
        await tg("answerCallbackQuery", callback_query_id=cq_id)
        uid = int(data.split("_")[1])
        old_caption = query["message"].get("caption", "")
        await tg("editMessageCaption", chat_id=chat_id, message_id=msg_id,
                 caption=old_caption + "\n\n❌ Rad etildi.", parse_mode="HTML")
        _, sdata = db.get_state(str(uid))
        user_chat = None
        if sdata:
            try: user_chat = json.loads(sdata).get("chat_id")
            except: pass
        if not user_chat and uid in pending_payments:
            user_chat = pending_payments.pop(uid)["chat_id"]
        if user_chat:
            await tg("sendMessage", chat_id=user_chat,
                     text=f"❌ To'lovingiz tasdiqlanmadi.\n\nSavol bo'lsa: {PAYMENT_ADMIN}")
        return JSONResponse({"ok": True})

    # Foydalanuvchiga javob berish
    if data.startswith("reply_"):
        if from_id != ADMIN_ID:
            await tg("answerCallbackQuery", callback_query_id=cq_id, text="⛔ Ruxsat yo'q.", show_alert=True)
            return JSONResponse({"ok": True})
        target_id = data.replace("reply_", "")
        await tg("answerCallbackQuery", callback_query_id=cq_id)
        db.set_state(str(from_id), "admin_reply", target_id)
        await tg("sendMessage", chat_id=chat_id,
            text=f"✉️ <b>Javob yozing</b>\n\nID <code>{target_id}</code> ga yuboriladi:\n\n❌ Bekor: /start",
            parse_mode="HTML")
        return JSONResponse({"ok": True})

    # 🧮 Kalkulator callback
    if data.startswith("c_"):
        await tg("answerCallbackQuery", callback_query_id=cq_id)
        uid = str(from_id)
        action = data[2:]
        expr = _calc_expr.get(uid, "")

        if action == "menu":
            _calc_expr[uid] = ""
            await tg("editMessageText", chat_id=chat_id, message_id=msg_id,
                text="🧮 <b>CalcBot</b>\n\nQuyidagi tugmalardan birini tanlang:",
                parse_mode="HTML", reply_markup=_calc_menu_kb())
        elif action == "mode_basic":
            await tg("editMessageText", chat_id=chat_id, message_id=msg_id,
                text=f"🧮 <b>Kalkulator</b>\n\n<code>{expr or '0'}</code>",
                parse_mode="HTML", reply_markup=_calc_kb("basic"))
        elif action == "mode_science":
            await tg("editMessageText", chat_id=chat_id, message_id=msg_id,
                text=f"🔬 <b>Ilmiy kalkulator</b>\n\n<code>{expr or '0'}</code>",
                parse_mode="HTML", reply_markup=_calc_kb("science"))
        elif action == "history":
            hist = _calc_history.get(uid, [])
            text_h = ("📜 <b>Tarix</b>\n\nHali hisoblashlar yo'q." if not hist else
                "📜 <b>Oxirgi hisoblashlar:</b>\n\n" +
                "\n".join(f"{i+1}. <code>{e}</code> = <b>{r}</b>" for i,(e,r) in enumerate(hist)))
            await tg("editMessageText", chat_id=chat_id, message_id=msg_id,
                text=text_h, parse_mode="HTML", reply_markup=_calc_history_kb())
        elif action == "clear_history":
            _calc_history[uid] = []
            await tg("editMessageText", chat_id=chat_id, message_id=msg_id,
                text="🗑 <b>Tarix tozalandi!</b>", parse_mode="HTML", reply_markup=_calc_history_kb())
        elif action == "open_currency":
            await tg("editMessageText", chat_id=chat_id, message_id=msg_id,
                text="💱 <b>Valyuta Konvertori</b>\n\nYo'nalishni tanlang:",
                parse_mode="HTML", reply_markup=_calc_currency_kb())
        elif action == "open_convert":
            await tg("editMessageText", chat_id=chat_id, message_id=msg_id,
                text="📏 <b>Birlik O'zgartirish</b>\n\nYo'nalishni tanlang:",
                parse_mode="HTML", reply_markup=_calc_convert_kb())
        elif action.startswith("cur_"):
            parts = action[4:].split("_")
            from_cur, to_cur = parts[0], parts[1]
            _calc_awaiting[uid] = {"type": "currency", "from": from_cur, "to": to_cur}
            await tg("editMessageText", chat_id=chat_id, message_id=msg_id,
                text=f"💱 <b>{from_cur} → {to_cur}</b>\n\nMiqdorni yozing (masalan: <code>100</code>):",
                parse_mode="HTML")
        elif action.startswith("conv_"):
            conv_type = action[5:]
            _calc_awaiting[uid] = {"type": "convert", "conv_type": conv_type}
            labels = {"km_mi":"km ↔ mi","kg_lb":"kg ↔ lb","c_f":"°C ↔ °F","m_ft":"m ↔ ft"}
            await tg("editMessageText", chat_id=chat_id, message_id=msg_id,
                text=f"📏 <b>{labels.get(conv_type, conv_type)}</b>\n\nMiqdorni yozing:",
                parse_mode="HTML")
        elif action == "C":
            _calc_expr[uid] = ""
            mode = "basic"
            await tg("editMessageText", chat_id=chat_id, message_id=msg_id,
                text="🧮 <b>Kalkulator</b>\n\n<code>0</code>",
                parse_mode="HTML", reply_markup=_calc_kb(mode))
        elif action == "back":
            expr = expr[:-1]
            _calc_expr[uid] = expr
            sci = any(f in expr for f in ["sin","cos","tan","log","ln","sqrt","π"])
            mode = "science" if sci else "basic"
            title = "🔬 <b>Ilmiy kalkulator</b>" if sci else "🧮 <b>Kalkulator</b>"
            try:
                await tg("editMessageText", chat_id=chat_id, message_id=msg_id,
                    text=f"{title}\n\n<code>{expr or '0'}</code>",
                    parse_mode="HTML", reply_markup=_calc_kb(mode))
            except: pass
        elif action == "=":
            if expr:
                try:
                    result = safe_calc(expr)
                    formatted = format_result(result)
                    hist = _calc_history.get(uid, [])
                    hist.append((expr, formatted))
                    if len(hist) > 10: hist = hist[-10:]
                    _calc_history[uid] = hist
                    _calc_expr[uid] = str(result)
                    await tg("editMessageText", chat_id=chat_id, message_id=msg_id,
                        text=f"🧮 <b>Natija</b>\n\n<code>{expr}</code>\n━━━━━━━━━━━━━\n✅ <b>{formatted}</b>",
                        parse_mode="HTML", reply_markup=_calc_result_kb())
                except CalcError as e:
                    await tg("answerCallbackQuery", callback_query_id=cq_id,
                        text=f"❌ {str(e)}", show_alert=True)
        else:
            if action == "^2": expr += "^2"
            elif action == "1/x": expr = f"1/({expr})" if expr else "1/"
            else: expr += action
            _calc_expr[uid] = expr
            sci = any(f in expr for f in ["sin","cos","tan","log","ln","sqrt","π"])
            mode = "science" if sci else "basic"
            title = "🔬 <b>Ilmiy kalkulator</b>" if sci else "🧮 <b>Kalkulator</b>"
            try:
                await tg("editMessageText", chat_id=chat_id, message_id=msg_id,
                    text=f"{title}\n\n<code>{expr or '0'}</code>",
                    parse_mode="HTML", reply_markup=_calc_kb(mode))
            except: pass
        return JSONResponse({"ok": True})

    # Admin panel tugmalari
    if data.startswith("admin_"):
        if from_id != ADMIN_ID:
            await tg("answerCallbackQuery", callback_query_id=cq_id, text="⛔ Ruxsat yo'q.", show_alert=True)
            return JSONResponse({"ok": True})
        await tg("answerCallbackQuery", callback_query_id=cq_id)

        if data == "admin_stats":
            report = db.get_stats_report()
            await tg("sendMessage", chat_id=chat_id, text=report, parse_mode="HTML")

        elif data == "admin_plusadd":
            db.set_state(str(from_id), "admin_plusadd_id")
            await tg("sendMessage", chat_id=chat_id,
                text="➕ <b>Plus berish</b>\n\nFoydalanuvchi ID sini yuboring:\n<i>Misol: 123456789</i>",
                parse_mode="HTML")

        elif data == "admin_plusremove":
            db.set_state(str(from_id), "admin_plusremove_id")
            await tg("sendMessage", chat_id=chat_id,
                text="➖ <b>Plus o'chirish</b>\n\nFoydalanuvchi ID sini yuboring:\n<i>Misol: 123456789</i>",
                parse_mode="HTML")

        elif data == "admin_pluscheck":
            db.set_state(str(from_id), "admin_pluscheck_id")
            await tg("sendMessage", chat_id=chat_id,
                text="🔍 <b>Plus tekshirish</b>\n\nFoydalanuvchi ID sini yuboring:\n<i>Misol: 123456789</i>",
                parse_mode="HTML")

        elif data == "admin_userlist":
            users = db.get_all_users_info()
            if not users:
                await tg("sendMessage", chat_id=chat_id, text="👤 Hozirda foydalanuvchilar yo'q.")
            else:
                lines = [f"👤 <b>Barcha foydalanuvchilar ({len(users)} ta):</b>\n"]
                for u in users:
                    name = f"@{u['username']}" if u['username'] else "—"
                    badge = "💎" if u['is_plus'] else "🆓"
                    lines.append(f"{badge} <code>{u['user_id']}</code> | {name} | {u['join_date']}")
                text_out = "\n".join(lines)
                for i in range(0, len(text_out), 4000):
                    await tg("sendMessage", chat_id=chat_id, text=text_out[i:i+4000], parse_mode="HTML")

        elif data == "admin_pluslist":
            users = db.get_premium_users()
            if not users:
                await tg("sendMessage", chat_id=chat_id, text="👥 Hozirda faol Plus foydalanuvchilar yo'q.")
            else:
                lines = [f"👥 <b>Faol Plus foydalanuvchilar ({len(users)} ta):</b>\n"]
                for u in users:
                    name = u["username"] or "—"
                    lines.append(f"• <code>{u['user_id']}</code> | {name} | {fmt_date(u['until'])} gacha")
                await tg("sendMessage", chat_id=chat_id, text="\n".join(lines), parse_mode="HTML")

        elif data == "admin_broadcast":
            db.set_state(str(from_id), "waiting_broadcast")
            await tg("sendMessage", chat_id=chat_id,
                text="📢 <b>Reklama yuborish</b>\n\nXabarni yozing (matn, rasm yoki video):\n\n❌ Bekor: /start",
                parse_mode="HTML")

        return JSONResponse({"ok": True})

    await tg("answerCallbackQuery", callback_query_id=cq_id)
    return JSONResponse({"ok": True})


@app.post("/webhook/bot")
async def webhook_handler(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
    except:
        return JSONResponse({"ok": True})

    if "callback_query" in data:
        return await handle_callback_query(data["callback_query"])

    if "message" not in data:
        return JSONResponse({"ok": True})

    msg = data["message"]
    chat_id = msg["chat"]["id"]
    user_id = str(msg["from"]["id"])
    first_name = msg["from"].get("first_name", "Foydalanuvchi")
    username = msg["from"].get("username", "")
    text = msg.get("text", "")
    photo = msg.get("photo")
    audio = msg.get("audio") or msg.get("voice")

    state, state_data = db.get_state(user_id)
    print(f"[*] from={user_id} state={state} text={text[:30] if text else ''}")

    # /stats — barcha foydalanuvchilar uchun (o'z hisobi)
    if text == "/stats":
        used = db.get_daily_smm(user_id)
        prem = db.is_premium(user_id)
        if prem:
            until = db.get_user_metadata(user_id).get("premium_until", "")
            status = f"💎 Plus ({fmt_date(until)} gacha)"
            limit_text = f"{used}/{SMM_PREMIUM_DAILY} ta ishlatildi"
        else:
            status = "🆓 Free"
            limit_text = f"{used}/{SMM_FREE_DAILY} ta ishlatildi"
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": (
                f"📊 <b>Sizning hisobingiz</b>\n\n"
                f"👤 Tarif: {status}\n"
                f"📝 SMM bugun: {limit_text}\n"
                f"🆔 ID: <code>{user_id}</code>"
            ),
            "parse_mode": "HTML"
        })

    # /admin — faqat admin uchun panel
    if text == "/admin":
        if int(user_id) != ADMIN_ID:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": "⛔ Ruxsat yo'q."})
        db.set_state(user_id, None)
        keyboard = {"inline_keyboard": [
            [{"text": "📊 Statistika", "callback_data": "admin_stats"}],
            [{"text": "➕ Plus berish", "callback_data": "admin_plusadd"},
             {"text": "➖ Plus o'chirish", "callback_data": "admin_plusremove"}],
            [{"text": "🔍 Plus tekshirish", "callback_data": "admin_pluscheck"},
             {"text": "👥 Plus ro'yxati", "callback_data": "admin_pluslist"}],
            [{"text": "👤 Foydalanuvchilar", "callback_data": "admin_userlist"}],
            [{"text": "📢 Reklama", "callback_data": "admin_broadcast"}],
        ]}
        return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
            "text": "👑 <b>Admin Panel</b>\n\nQuyidagi amallardan birini tanlang:",
            "parse_mode": "HTML", "reply_markup": keyboard})

    # /reklama — faqat admin uchun
    if text == "/reklama":
        if int(user_id) != ADMIN_ID:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": "⛔ Ruxsat yo'q."})
        db.set_state(user_id, "waiting_broadcast")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": (
                "📢 <b>Reklama yuborish</b>\n\n"
                "Yubormoqchi bo'lgan xabarni yozing.\n"
                "Rasm, video yoki matn bo'lishi mumkin.\n\n"
                "❌ Bekor qilish: /start"
            ),
            "parse_mode": "HTML"
        })

    # /start
    if text == "/start":
        db.set_state(user_id, None)
        try: db.add_user(user_id, first_name)
        except: pass
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": (
                f"Xush kelibsiz, {first_name}! 👋\n\n"
                f"🤖 <b>Sadoon AI</b> — sizning aqlli yordamchingiz!\n\n"
                f"🆓 <b>Bepul xizmatlar:</b>\n"
                f"📥 Video yuklab olish — TikTok, Instagram, YouTube\n"
                f"🌐 Tilmoch AI — O'zbek ↔ Rus ↔ Xitoy\n"
                f"🤖 AI Suhbat — savol-javob, maslahat, yordam\n"
                f"🧮 Kalkulator — oddiy, ilmiy, valyuta, birlik\n"
                f"🎬 Klip yaratish — rasm + musiqa\n\n"
                f"💎 <b>Plus xizmatlar ({SMM_FREE_DAILY} ta/kun bepul):</b>\n"
                f"✍️ SMM Studio — AI yordamida kontent yaratish\n"
                f"   📝 Post • 🎬 Reels • 📅 Plan\n"
                f"   #️⃣ Hashtag • 💬 Caption • 📊 Strategiya\n\n"
                f"📌 Boshlash uchun quyidagi tugmalardan foydalaning 👇"
            ),
            "parse_mode": "HTML",
            "reply_markup": MAIN_KB
        })

    # 📊 Mening limitim
    if text == "📊 Mening limitim":
        used = db.get_daily_smm(user_id)
        prem = db.is_premium(user_id)
        if prem:
            until = db.get_user_metadata(user_id).get("premium_until", "")
            return JSONResponse({
                "method": "sendMessage", "chat_id": chat_id,
                "text": f"💎 <b>Plus aktiv</b>\n\n📅 {fmt_date(until)} gacha\n✅ Kuniga {SMM_PREMIUM_DAILY} ta SMM so'rov",
                "parse_mode": "HTML", "reply_markup": PAID_KB
            })
        remaining = max(0, SMM_FREE_DAILY - used)
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": (
                f"📊 <b>Kunlik limitingiz</b>\n\n"
                f"📝 SMM bugun: {used}/{SMM_FREE_DAILY} ta\n"
                f"🆓 Qoldi: {remaining} ta\n\n"
                f"💎 Ko'proq ishlash uchun Plus oling!"
            ),
            "parse_mode": "HTML", "reply_markup": PAID_KB
        })

    # 💎 Plus olish
    if text == "💎 Plus olish":
        keyboard = {"inline_keyboard": [
            [{"text": "⭐ Plus — 29,000 so'm/oy", "callback_data": "pay_starter"}],
        ]}
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": (
                f"💎 <b>Plus Rejim</b>\n\n"
                f"✅ Kuniga {SMM_PREMIUM_DAILY} ta SMM so'rov\n"
                f"🆓 Bepul: kuniga {SMM_FREE_DAILY} ta\n\n"
                f"💰 <b>Narx:</b> 29,000 so'm/oy\n\n"
                f"Tarif tanlang 👇"
            ),
            "parse_mode": "HTML", "reply_markup": keyboard
        })

    # 🆓 Bepul xizmatlar
    if text == "🆓 Bepul xizmatlar":
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "🆓 <b>Bepul xizmatlar</b>\n\nBitta tanlang:",
            "parse_mode": "HTML", "reply_markup": FREE_KB
        })

    # 💎 Pullik xizmatlar
    if text == "💎 Pullik xizmatlar":
        used = db.get_daily_smm(user_id)
        prem = db.is_premium(user_id)
        if prem:
            until = db.get_user_metadata(user_id).get("premium_until", "")
            info = f"💎 Plus aktiv ({fmt_date(until)} gacha) — {SMM_PREMIUM_DAILY} ta/kun"
        else:
            remaining = max(0, SMM_FREE_DAILY - used)
            info = f"🆓 Bugun qoldi: {remaining}/{SMM_FREE_DAILY} ta bepul so'rov"
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": f"💎 <b>Pullik xizmatlar</b>\n\n{info}\n\nBitta tanlang:",
            "parse_mode": "HTML", "reply_markup": PAID_KB
        })

    # 🔙 Orqaga
    if text == "🔙 Orqaga":
        db.set_state(user_id, None)
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "Asosiy menyu:", "reply_markup": MAIN_KB
        })

    # 📥 Yuklab olish
    if text == "📥 Yuklab olish":
        db.set_state(user_id, "waiting_download")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "🔗 Instagram, TikTok yoki YouTube havolasini yuboring."
        })

    # 🧮 Kalkulator
    if text == "🧮 Kalkulator":
        _calc_expr[user_id] = ""
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "🧮 <b>CalcBot</b>\n\nQuyidagi tugmalardan birini tanlang:",
            "parse_mode": "HTML", "reply_markup": _calc_menu_kb()
        })

    # 🤖 AI Suhbat
    if text == "🤖 AI Suhbat":
        db.set_state(user_id, "waiting_chat", "[]")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": (
                "🤖 <b>AI Suhbat</b>\n\n"
                "Menga istalgan savol bering — javob beraman!\n"
                "O'zbek, Rus yoki Ingliz tilida yozishingiz mumkin.\n\n"
                "🔙 Chiqish uchun <b>Orqaga</b> tugmasini bosing."
            ),
            "parse_mode": "HTML",
            "reply_markup": {"keyboard": [[{"text": "🔙 Orqaga"}]], "resize_keyboard": True}
        })

    # 🔍 Shazam
    if text == "🔍 Shazam":
        db.set_state(user_id, "waiting_shazam")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": (
                "🔍 <b>Shazam</b>\n\n"
                "Qo'shiqni aniqlash uchun:\n"
                "🎵 Audio fayl yuboring\n"
                "🎬 Video fayl yuboring\n"
                "🔗 Yoki YouTube/TikTok/Instagram havolasi yuboring"
            ),
            "parse_mode": "HTML"
        })

    # 🎬 Klip Yaratish
    if text == "🎬 Klip Yaratish":
        db.set_state(user_id, "waiting_clip_photo")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "🖼️ Rasm yuboring."
        })

    # 🌐 Tilmoch AI
    if text == "🌐 Tilmoch AI":
        db.set_state(user_id, "waiting_translate")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "✍️ Tarjima qilinadigan matnni yuboring."
        })

    # ✍️ Takliflar
    if text == "✍️ Takliflar":
        db.set_state(user_id, "waiting_feedback")
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

    if text == "📝 Post yozish":
        db.set_state(user_id, "smm_post")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "📝 Qaysi mavzuda post yozay?\n\n<i>Misol: Go'zallik saloni uchun aktsiya posti</i>",
            "parse_mode": "HTML"
        })

    if text == "🎬 Reels ssenariy":
        db.set_state(user_id, "smm_reels")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "🎬 Qanday mavzuda reels ssenariy yozay?\n\n<i>Misol: Kafe uchun 'bir kunim' formatida reels</i>",
            "parse_mode": "HTML"
        })

    if text == "📅 Kontent plan":
        db.set_state(user_id, "smm_plan")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "📅 Qaysi nisha uchun 30 kunlik plan tuzay?\n\n<i>Misol: Online kiyim do'koni</i>",
            "parse_mode": "HTML"
        })

    if text == "#️⃣ Hashtag":
        db.set_state(user_id, "smm_hashtag")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "#️⃣ Qaysi mavzu uchun hashtag kerak?\n\n<i>Misol: Fitness va sport ozuqa</i>",
            "parse_mode": "HTML"
        })

    if text == "💬 Caption":
        db.set_state(user_id, "smm_caption")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "💬 Rasm tavsifi yoki mavzuni yozing:\n\n<i>Misol: Yangi kolleksiya keldi, stilist fotosessiya</i>",
            "parse_mode": "HTML"
        })

    if text == "📊 Strategiya":
        db.set_state(user_id, "smm_strategy")
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "📊 Biznes turingiz va maqsadingizni yozing:\n\n<i>Misol: Stomatologiya klinikasi, Instagram orqali mijoz jalb qilish</i>",
            "parse_mode": "HTML"
        })

    # --- STATE HANDLERS ---

    if state == "waiting_download" and text:
        urls = re.findall(r'https?://[^\s]+', text)
        if urls:
            db.set_state(user_id, None)
            url = urls[0].strip('.,()!?')
            background_tasks.add_task(bg_download, chat_id, user_id, url)
            return JSONResponse({
                "method": "sendMessage", "chat_id": chat_id,
                "text": "⏳ Video yuklanmoqda, biroz kuting...\n\n(Instagram uchun 30-40 soniya kerak bo'lishi mumkin)"
            })
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "❌ Havola topilmadi. Iltimos, to'g'ri URL yuboring."
        })

    if state == "waiting_shazam":
        db.set_state(user_id, None)
        a = f"temp/shazam_{uuid.uuid4()}.mp3"
        if audio:
            await tg_download(audio["file_id"], a)
            background_tasks.add_task(bg_shazam, chat_id, a)
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": "🔍 Qo'shiq aniqlanmoqda..."})
        elif msg.get("video") or msg.get("video_note"):
            file_id = (msg.get("video") or msg.get("video_note"))["file_id"]
            await tg_download(file_id, a)
            background_tasks.add_task(bg_shazam, chat_id, a)
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": "🔍 Qo'shiq aniqlanmoqda..."})
        elif text:
            urls = re.findall(r'https?://[^\s]+', text)
            if urls:
                background_tasks.add_task(bg_shazam_url, chat_id, user_id, urls[0].strip('.,()!?'), a)
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                    "text": "⏳ Audio yuklanmoqda, qo'shiq aniqlanmoqda..."})
        return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
            "text": "❌ Audio fayl, video yoki havola yuboring."})

    if state == "waiting_translate" and text:
        db.set_state(user_id, None)
        result = None
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
        # 3. Fallback: MyMemory (bepul, kalitsiz)
        if not result:
            try:
                import urllib.parse as _up
                q = _up.quote(text[:500])
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        f"https://api.mymemory.translated.net/get?q={q}&langpair=auto|uz",
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as r:
                        mdata = await r.json()
                        if mdata.get("responseStatus") == 200:
                            t = mdata["responseData"]["translatedText"]
                            result = f"🌐 Tarjima:\n{t}"
                        else:
                            print(f"[!] MyMemory xato: {mdata}")
            except Exception as e:
                print(f"[!] MyMemory fallback xato: {e}")
        if not result:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": "❌ Tarjima qilib bo'lmadi. Keyinroq urinib ko'ring."})
        db.log_stats(user_id, "translate")
        return JSONResponse({"method": "sendMessage", "chat_id": chat_id, "text": result})

    if state and state.startswith("waiting_payment_") and text and not photo:
        plan = state.replace("waiting_payment_", "")
        info = PLAN_INFO.get(plan, {})
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": (
                f"📸 Iltimos, to'lov chekining <b>screenshot</b>ini yuboring.\n\n"
                f"📌 Tarif: {info.get('name', '')}\n"
                f"❌ Bekor qilish: /start"
            ),
            "parse_mode": "HTML"
        })

    if state and state.startswith("waiting_payment_") and photo:
        plan = state.replace("waiting_payment_", "")
        if plan not in PLAN_INFO:
            return JSONResponse({"ok": True})
        info = PLAN_INFO[plan]
        db.set_state(user_id, "pending_payment", json.dumps({"plan": plan, "chat_id": chat_id}))
        pending_payments[int(user_id)] = {"plan": plan, "chat_id": chat_id}
        keyboard = {"inline_keyboard": [[
            {"text": f"✅ {info['days']} kun Plus", "callback_data": f"approve_{user_id}_{info['days']}"},
            {"text": "❌ Rad etish", "callback_data": f"reject_{user_id}"},
        ]]}
        await tg("sendPhoto", chat_id=ADMIN_ID,
                 photo=photo[-1]["file_id"],
                 caption=(
                     f"💳 <b>To'lov so'rovi</b>\n\n"
                     f"👤 {first_name}\n"
                     f"🆔 ID: <code>{user_id}</code>\n"
                     f"📌 Tarif: {info['name']}\n"
                     f"💵 Narx: {info['price']}"
                 ),
                 parse_mode="HTML", reply_markup=keyboard)
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "✅ Chekingiz adminga yuborildi!\n⏳ Tez orada plus faollashtiriladi."
        })

    if state == "waiting_clip_photo":
        if not photo:
            return JSONResponse({
                "method": "sendMessage", "chat_id": chat_id,
                "text": "🖼️ Iltimos, rasm (foto) yuboring."
            })
        photo_id = photo[-1]["file_id"]
        db.set_state(user_id, "waiting_clip_audio", photo_id)
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "🎵 Endi audio yuboring.\n\n📎 Audio fayl <b>yoki</b> TikTok/Instagram/YouTube havolasi yuborishingiz mumkin.",
            "parse_mode": "HTML"
        })

    if state == "waiting_clip_audio":
        photo_id = state_data
        db.set_state(user_id, None)
        p = f"temp/p_{uuid.uuid4()}.jpg"
        v = f"output/v_{uuid.uuid4()}.mp4"
        tmp_v = f"temp/tv_{uuid.uuid4()}.mp4"
        try:
            await tg_download(photo_id, p)

            if audio:
                raw_a = f"temp/ar_{uuid.uuid4()}"
                a = f"temp/a_{uuid.uuid4()}.m4a"
                await tg_download(audio["file_id"], raw_a)
                # M4A ga convert qilamiz
                cmd_conv = [
                    "ffmpeg", "-y", "-i", raw_a,
                    "-vn", "-c:a", "aac", "-b:a", "128k",
                    "-f", "mp4", "-movflags", "+faststart", a
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd_conv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await proc.communicate()
                if os.path.exists(raw_a): os.remove(raw_a)
                audio_ok = os.path.exists(a) and os.path.getsize(a) > 100
            elif text:
                urls = re.findall(r'https?://[^\s]+', text)
                if not urls:
                    return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                        "text": "❌ Havola topilmadi. Audio fayl yoki link yuboring."})
                url = urls[0].strip('.,()!?')
                a_base = f"temp/a_{uuid.uuid4()}"
                # bestaudio yuklab, orijinal formatda saqlash
                actual_a = await asyncio.wait_for(
                    mixer.download_audio_raw(url, a_base), timeout=55
                )
                if not actual_a:
                    return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                        "text": "❌ Musiqa yuklab bo'lmadi. Boshqa havola yoki audio fayl yuboring."})
                a = actual_a
                audio_ok = True
            else:
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                    "text": "❌ Audio fayl yoki havola yuboring."})

            background_tasks.add_task(bg_mix_clip, chat_id, user_id, p, a, v)
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": "⏳ Klip tayyorlanmoqda, biroz kuting..."})
        except asyncio.TimeoutError:
            for f in [p, a, tmp_v]:
                if os.path.exists(f): os.remove(f)
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": "⏰ Vaqt tugadi. Qisqaroq video sinab ko'ring."})
        except Exception as e:
            for f in [p, a, tmp_v]:
                if os.path.exists(f): os.remove(f)
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": f"❌ Xato: {str(e)[:200]}"})

    if state == "waiting_broadcast" and int(user_id) == ADMIN_ID:
        db.set_state(user_id, None)
        background_tasks.add_task(bg_broadcast, chat_id, msg)
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "⏳ Reklama yuborilmoqda..."
        })

    if state == "waiting_feedback" and text:
        db.set_state(user_id, None)
        keyboard = {"inline_keyboard": [
            [{"text": "✉️ Javob berish", "callback_data": f"reply_{user_id}"}]
        ]}
        background_tasks.add_task(
            tg, "sendMessage",
            chat_id=int(ADMIN_ID),
            text=f"📩 Taklif:\n👤 {first_name}{' (@' + username + ')' if username else ''}\n🆔 {user_id}\n\n{text}",
            reply_markup=keyboard
        )
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "✅ Taklifingiz adminga yuborildi. Rahmat!"
        })

    if state in ("smm_post", "smm_reels", "smm_plan", "smm_hashtag", "smm_caption", "smm_strategy") and text:
        is_prem = db.is_premium(user_id)
        used = db.get_daily_smm(user_id)
        daily_limit = SMM_PREMIUM_DAILY if is_prem else SMM_FREE_DAILY
        if used >= daily_limit:
            db.set_state(user_id, None)
            keyboard = {"inline_keyboard": [
                [{"text": "⭐ Plus — 29,000 so'm/oy", "callback_data": "pay_starter"}],
            ]}
            return JSONResponse({
                "method": "sendMessage", "chat_id": chat_id,
                "text": (
                    f"⚠️ <b>Kunlik limit tugadi!</b>\n\n"
                    f"📝 Bugun {used}/{daily_limit} ta so'rov ishlatildi.\n\n"
                    f"💎 Ko'proq ishlash uchun Plus oling:"
                ),
                "parse_mode": "HTML", "reply_markup": keyboard
            })
        if not openai_client:
            db.set_state(user_id, None)
            return JSONResponse({
                "method": "sendMessage", "chat_id": chat_id,
                "text": "❌ OpenAI API kalit sozlanmagan.", "reply_markup": SMM_KB
            })
        mode = state
        db.set_state(user_id, None)
        background_tasks.add_task(bg_smm, chat_id, user_id, text, mode)
        return JSONResponse({
            "method": "sendMessage", "chat_id": chat_id,
            "text": "⏳ SMM AI ishlamoqda..."
        })

    # 🤖 AI Suhbat state
    if state == "waiting_chat" and text:
        if text == "🔙 Orqaga":
            db.set_state(user_id, None)
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": "Asosiy menyu:", "reply_markup": MAIN_KB})
        if not groq_client:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": "❌ AI sozlanmagan."})
        try:
            history = json.loads(state_data) if state_data else []
        except: history = []
        history.append({"role": "user", "content": text})
        if len(history) > 20: history = history[-20:]
        try:
            resp = await asyncio.wait_for(
                groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "system", "content": (
                        "Sen Sadoon AI — aqlli va do'stona yordamchi. "
                        "O'zbek, Rus va Ingliz tillarini bilasan. "
                        "Foydalanuvchi qaysi tilda yozsa, o'sha tilda javob ber. "
                        "Qisqa, aniq va foydali javob ber."
                    )}] + history,
                    max_tokens=1000, temperature=0.7,
                ), timeout=30
            )
            reply = resp.choices[0].message.content
            history.append({"role": "assistant", "content": reply})
            db.set_state(user_id, "waiting_chat", json.dumps(history))
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": reply[:4000],
                "reply_markup": {"keyboard": [[{"text": "🔙 Orqaga"}]], "resize_keyboard": True}})
        except asyncio.TimeoutError:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": "⏰ Javob kelmadi. Qaytadan urinib ko'ring."})
        except Exception as e:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": f"❌ Xatolik: {str(e)[:200]}"})

    # 🧮 Kalkulator callback (awaiting text input)
    if _calc_awaiting.get(user_id) and text:
        awaiting = _calc_awaiting.pop(user_id)
        try:
            amount = float(text.replace(",", "").replace(" ", ""))
        except:
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": "❌ Raqam kiriting (masalan: 100)"})
        if awaiting["type"] == "currency":
            try:
                result = await _convert_currency(amount, awaiting["from"], awaiting["to"])
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                    "text": (f"💱 <b>Valyuta konvertatsiyasi</b>\n\n"
                             f"<code>{amount:,.2f} {awaiting['from']}</code>\n━━━━━━━━━━━━━\n"
                             f"✅ <b>{result:,.2f} {awaiting['to']}</b>"),
                    "parse_mode": "HTML", "reply_markup": _calc_result_kb()})
            except Exception as e:
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                    "text": f"❌ {e}", "reply_markup": _calc_currency_kb()})
        elif awaiting["type"] == "convert":
            try:
                result = _convert_unit(amount, awaiting["conv_type"])
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                    "text": result, "parse_mode": "HTML", "reply_markup": _calc_result_kb()})
            except Exception as e:
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                    "text": f"❌ {e}", "reply_markup": _calc_convert_kb()})

    # Admin state handlerlari
    if int(user_id) == ADMIN_ID and text:

        if state == "admin_plusadd_id":
            if not text.isdigit():
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                    "text": "❌ Faqat raqam kiriting (User ID):"})
            if not db.user_exists(text):
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                    "text": f"❌ ID <code>{text}</code> bazada topilmadi. Foydalanuvchi botni ishga tushirgandirmi?",
                    "parse_mode": "HTML"})
            db.set_state(user_id, "admin_plusadd_days", text)
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": f"✅ ID: <code>{text}</code>\n\nNecha kun Plus berilsin?",
                "parse_mode": "HTML"})

        if state == "admin_plusadd_days":
            if not text.isdigit():
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                    "text": "❌ Faqat raqam kiriting (kunlar soni):"})
            target_id = state_data
            days = int(text)
            until = db.activate_premium(target_id, days)
            db.set_state(user_id, None)
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": f"✅ <code>{target_id}</code> ga {days} kun Plus berildi\n📅 {fmt_date(until)} gacha",
                "parse_mode": "HTML"})

        if state == "admin_plusremove_id":
            if not text.isdigit():
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                    "text": "❌ Faqat raqam kiriting (User ID):"})
            if not db.user_exists(text):
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                    "text": f"❌ ID <code>{text}</code> bazada topilmadi.",
                    "parse_mode": "HTML"})
            meta = db.get_user_metadata(text)
            meta.pop("premium_until", None)
            db.set_user_metadata(text, meta)
            db.set_state(user_id, None)
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": f"✅ <code>{text}</code> dan Plus o'chirildi",
                "parse_mode": "HTML"})

        if state == "admin_pluscheck_id":
            if not text.isdigit():
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                    "text": "❌ Faqat raqam kiriting (User ID):"})
            if not db.user_exists(text):
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                    "text": f"❌ ID <code>{text}</code> bazada topilmadi.",
                    "parse_mode": "HTML"})
            meta = db.get_user_metadata(text)
            until = meta.get("premium_until", "")
            prem = db.is_premium(text)
            smm_used = db.get_daily_smm(text)
            status = f"💎 Plus aktiv — {fmt_date(until)} gacha" if prem else "🆓 Free"
            db.set_state(user_id, None)
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": (
                    f"👤 ID: <code>{text}</code>\n"
                    f"📊 Tarif: {status}\n"
                    f"📝 Bugun SMM: {smm_used} ta"
                ), "parse_mode": "HTML"})

        if state == "admin_reply":
            target_id = state_data
            db.set_state(user_id, None)
            await_result = await tg("sendMessage", chat_id=int(target_id),
                text=f"📬 <b>Admin javobi:</b>\n\n{text}", parse_mode="HTML")
            if await_result.get("ok"):
                return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                    "text": f"✅ Javob yuborildi → <code>{target_id}</code>", "parse_mode": "HTML"})
            return JSONResponse({"method": "sendMessage", "chat_id": chat_id,
                "text": "❌ Yuborishda xatolik. Foydalanuvchi botni bloklagan bo'lishi mumkin."})

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
    state, data = db.get_state(user_id)
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

if __name__ == "__main__":
    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
