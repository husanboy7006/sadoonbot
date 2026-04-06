FROM python:3.11-slim

WORKDIR /app

# Muhitni tayyorlash (FFmpeg va brauzer kutubxonalari)
# Hugging Face da 'nodejs' o'zi kifoya, qo'shimcha repo shart emas.
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    gnupg2 \
    curl \
    nodejs \
    npm \
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

# Papkalarni yaratish va ruxsat berish
RUN mkdir -p temp output && chmod -R 777 /app

# Port 7860 uchun FastAPI start xizmati
# (server.py allaqachon mavjud bo'lishi kerak)
ENV PORT=7860
EXPOSE 7860

# start.sh ga ruxsat berish
RUN chmod +x start.sh

CMD ["./start.sh"]
