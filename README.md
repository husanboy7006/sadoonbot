---
title: Sadoon Api
emoji: 🎥
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# Sadoon AI - Media Downloader va Mixer Bot

Instagram, YouTube va TikTok media yuklab olish, musiqa aniqlash va video yaratish boti.

🚀 **Fixed universal support** (Invidious, TikWM, Cookies)

## 🚀 Tez Boshlash

### 1. Environment Variables Tayyorlash

`.env.example` faylini `.env` ga nusxalab, quyidagi qiymatlarni to'ldiring:

```bash
cp .env.example .env
```

**Majburiy qiymatlar:**
- `BOT_TOKEN` - Telegram Bot Token (@BotFather'dan olingan)
- `ADMIN_ID` - Sizning Telegram ID (bot admin uchun)
- `GEMINI_KEY` - Google Gemini API kaliti
- `SUPABASE_URL` - Supabase loyihasi URL
- `SUPABASE_KEY` - Supabase anon kaliti

### 2. Kutubxonalarni O'rnatish

```bash
pip install -r requirements.txt
```

### 3. Botni Ishga Tushirish

```bash
python bot.py
```

### 4. Serverni Ishga Tushirish (Webhook uchun)

```bash
python server.py
```

### 5. Docker bilan Ishga Tushirish

```bash
docker build -t sadoon-ai .
docker run -p 7860:7860 --env-file .env sadoon-ai
```

## 📋 Xususiyatlar

- 🎬 **Video Yuklab Olish**: Instagram, TikTok, YouTube
- 🎵 **Audio Yuklab Olish**: MP3 formatda
- 🔍 **Shazam**: Musiqani aniqlash
- 🎨 **CGI Product Artist**: AI bilan reklama rasmi yaratish
- 🌐 **AI Tarjimon**: Matnni tarjima qilish
- 💰 **Balans Tizimi**: Premium xizmatlar uchun

## 🔧 Konfiguratsiya

### Environment Variables

| Variable | Majburiy | Tavsif |
|----------|----------|--------|
| `BOT_TOKEN` | ✅ | Telegram Bot Token |
| `ADMIN_ID` | ✅ | Admin Telegram ID |
| `GEMINI_KEY` | ✅ | Google Gemini API Key |
| `SUPABASE_URL` | ✅ | Supabase Database URL |
| `SUPABASE_KEY` | ✅ | Supabase API Key |
| `BASE_URL` | ❌ | Webhook URL (default: localhost) |
| `SADOON_API_KEY` | ❌ | API endpoint uchun kalit |

### Cookies (Ixtiyoriy)

Instagram yuklab olish uchun `cookies.txt` faylini yarating (Netscape format).

## 🐛 Muammolar va Yechimlar

### Common Errors

1. **"ADMIN_ID environment variable not set!"**
   - `.env` faylida `ADMIN_ID` ni qo'shing

2. **"Supabase connection failed"**
   - SUPABASE_URL va SUPABASE_KEY ni tekshiring

3. **"Gemini API error"**
   - GEMINI_KEY ni yangilang

### Logs

Log fayllari:
- `bot.log` - Bot loglari
- `server.log` - Server loglari

## 📊 API Endpoints

- `GET /` - Status tekshirish
- `POST /webhook/bot` - Telegram webhook
- `POST /api/download-video` - Video yuklab olish API

## 🤝 Hissa Qo'shish

1. Fork qiling
2. Feature branch yarating (`git checkout -b feature/AmazingFeature`)
3. Commit qiling (`git commit -m 'Add some AmazingFeature'`)
4. Push qiling (`git push origin feature/AmazingFeature`)
5. Pull Request yarating

## 📄 Litsenziya

Bu loyiha MIT litsenziyasi ostida.

## ⚠️ Ogohlantirish

- Instagram cookies ishlatish Instagram TOS ga zid bo'lishi mumkin
- API kalitlarini hech qachon GitHub'ga push qilmang
- Production'da HTTPS ishlatish majburiy
