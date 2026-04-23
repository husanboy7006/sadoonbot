#!/bin/bash
echo "===== Application Startup at $(date '+%Y-%m-%d %H:%M:%S') ====="
echo ""

echo "Starting Sadoon API + Bot (Webhook Mode) on port 7860..."

# Tarmoq diagnostikasi
sleep 5
echo "=== NETWORK DIAGNOSTICS ==="
echo "Checking google.com..."
curl -I -s --connect-timeout 5 https://google.com | grep HTTP || echo "Google fails"
echo "==========================="

# Server + Bot (webhook mode) ni ishga tushirish
echo "Starting server with webhook bot..."
python -u server.py
