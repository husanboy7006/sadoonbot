from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "Sadoon API and Bot are running"}

@app.get("/api/mix")
def api_mix():
    return {"message": "API is online"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
