# HuggingFace Spaces va xalqaro serverlar uchun maxsus Docker muhiti
FROM python:3.11-slim

WORKDIR /app

# Serverga ffmpeg o'rnatamiz (Videolarni birlashtirish siri)
RUN apt-get update && apt-get install -y ffmpeg

# Kutubxonalarni o'rnatish
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Barcha fayllarni nusxalash
COPY . .

# HuggingFace 7860 portni qabul qiladi. Shuning uchun Botni ham, API'ni ham barvarak ishga tushiradigan komanda:
CMD python bot.py & uvicorn main:app --host 0.0.0.0 --port 7860
