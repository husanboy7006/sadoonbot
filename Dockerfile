FROM python:3.11-slim

WORKDIR /app

# Muhitni tayyorlash (Sadoon uchun faqat FFmpeg kerak)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Kutubxonalarni o'rnatish
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Barcha fayllarni nusxalash
COPY . .

# Papkalarni yaratish va ruxsat berish
RUN mkdir -p temp output && chmod -R 777 /app

# Hugging Face Spaces porti
ENV PORT=7860
EXPOSE 7860

# start.sh ga ruxsat berish
RUN chmod +x start.sh

CMD ["./start.sh"]
