from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import httpx
import logging
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

# =========================
# INIT
# =========================

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-ai")

app = FastAPI(
    title="MCP AI Gateway",
    version="1.0.1",
    description="Production-grade AI Gateway for Odoo ERP"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# =========================
# MODELS
# =========================

class ChatRequest(BaseModel):
    message: str | None = None
    question: str | None = None   # backward compatibility for old clients

class ChatResponse(BaseModel):
    reply: str

# =========================
# HEALTH
# =========================

@app.get("/health")
def health():
    return {"status": "ok"}

# =========================
# OPENAI CALL
# =========================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def call_openai(payload: dict):
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload
        )
    return r

# =========================
# CHAT API
# =========================

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):

    if not OPENAI_API_KEY:
        raise HTTPException(500, "OPENAI_API_KEY is not configured")

    # Accept both message & question
    prompt = req.message or req.question

    if not prompt:
        raise HTTPException(400, "Missing field: message or question")

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "You are a professional Odoo ERP AI assistant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }

    try:
        res = await call_openai(payload)
        data = res.json()

        if res.status_code != 200:
            logger.error("OpenAI Error: %s", data)
            return JSONResponse(
                status_code=502,
                content={"reply": data.get("error", {}).get("message", "OpenAI API Error")}
            )

        reply = data["choices"][0]["message"]["content"]
        return {"reply": reply}

    except httpx.RequestError as e:
        logger.exception("Connection error")
        return JSONResponse(
            status_code=500,
            content={"reply": f"Connection Error: {str(e)}"}
        )

    except Exception as e:
        logger.exception("Unexpected error")
        return JSONResponse(
            status_code=500,
            content={"reply": f"Internal Error: {str(e)}"}
        )