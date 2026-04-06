#!/bin/bash
echo "Starting FastAPI server on port 7860..."
python -u server.py &

# Kichik kutish (API tayyor bo'lishi uchun)
sleep 5

echo "Starting Telegram bot..."
# -u bayrog'i loglarni real vaqtda ko'rsatish uchun kerak
python -u bot.py
