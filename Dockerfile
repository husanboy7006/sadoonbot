FROM python:3.11-slim

WORKDIR /app

# Serverga ffmpeg, nodejs va Playwright uchun kerakli paketlarni o'rnatamiz
RUN apt-get update && apt-get install -y ffmpeg wget gnupg2 nodejs \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

# Kutubxonalarni o'rnatish
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright brauzerini o'rnatish (Chromium)
RUN python -m playwright install chromium

# Barcha fayllarni nusxalash
COPY . .

# Papkalarga ruxsat berish
RUN mkdir -p temp output && chmod -R 777 /app

# API va Bot aloqasi bitta Docker ichida
ENV API_URL="http://127.0.0.1:7860/api/mix"

# start.sh ga ruxsat beramiz va uni ishga tushiramiz
RUN chmod +x start.sh

CMD ["./start.sh"]
