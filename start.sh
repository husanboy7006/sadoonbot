#!/bin/bash
echo "Starting FastAPI server on port 7860..."
python -u server.py &

# API tayyor bo'lishini va tarmoq ochilishini 15 soniya kutamiz
echo "Waiting for Hugging Face network to become ready (15s)..."
sleep 15

# Tarmoq diagnostikasi
echo "=== NETWORK DIAGNOSTICS ==="
echo "Checking google.com..."
curl -I -s --connect-timeout 5 https://google.com | grep HTTP || echo "Google fails"
echo "Checking api.telegram.org via curl..."
curl -I -s --connect-timeout 5 https://api.telegram.org | grep HTTP || echo "Telegram API fails"
echo "Resolving api.telegram.org IP..."
getent hosts api.telegram.org || echo "Could not resolve Telegram DNS"
echo "==========================="

echo "Starting Telegram bot..."
python -u bot.py
