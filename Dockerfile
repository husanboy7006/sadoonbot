FROM python:3.11-slim

WORKDIR /app

# Serverga ffmpeg va ffmpeg-python ga kerakli paketlarni o'rnatamiz
RUN apt-get update && apt-get install -y ffmpeg

# Kutubxonalarni o'rnatish
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Barcha fayllarni nusxalash
COPY . .

# HuggingFace "user 1000" rejimida ishlagani uchun papkalarga barcha ruxsatlarni berib qo'yamiz (Permisson Error bermasligi uchun)
RUN mkdir -p temp output && chmod -R 777 /app

# API va Bot aloqasi bitta Docker ichida bo'lishligi uchun 7860-port ko'rsatilmoqda
ENV API_URL="http://127.0.0.1:7860/api/mix"

# start.sh ga ruxsat beramiz va uni ishga tushiramiz
RUN chmod +x start.sh

CMD ["./start.sh"]
