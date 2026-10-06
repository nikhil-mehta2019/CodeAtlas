from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/webhooks/stripe")
def stripe_webhook():
    return {"received": True}
