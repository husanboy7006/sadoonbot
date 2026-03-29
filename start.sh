#!/bin/bash

# FastAPI (backend) ni orqa fonda (background) yoqamiz
uvicorn main:app --host 0.0.0.0 --port 7860 &

# Telegram botni asosiy jarayon (foreground) sifatida yoqamiz
# Agar bot o'chib qolsa, Docker buni sezadi va restart beradi
python bot.py
