from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

# CORS sozlamalari (Vercel dagi sayt API bilan bog'lanishi uchun)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Hamma manzillardan so'rovlarni qabul qiladi
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "Sadoon API and Bot are running"}

@app.get("/api/mix")
def api_mix():
    return {"message": "API is online", "details": "CORS enabled for Sadoon AI (Vercel)"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
