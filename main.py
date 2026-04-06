from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import httpx
import logging
import base64 
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

class FileItem(BaseModel):
    name: str
    type: str
    data: str

class ChatRequest(BaseModel):
    message: str | None = None
    question: str | None = None   
    files: list[FileItem] | None = None # <-- NHẬN MẢNG FILE TỪ ODOO

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

    prompt_text = req.message or req.question or ""

    if not prompt_text and not req.files:
        raise HTTPException(400, "Missing field: message or files")

    text_content = prompt_text
    image_contents = []
    has_images = False

    if req.files:
        for f in req.files:
            if f.type.startswith("image/"):
                has_images = True
                image_contents.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{f.type};base64,{f.data}"}
                })
            elif f.type in ["text/csv", "text/plain"] or f.name.endswith(('.csv', '.txt')):
                try:
                    # Dịch file Base64 ra chữ Text và ghép thẳng vào câu hỏi
                    decoded_text = base64.b64decode(f.data).decode('utf-8')
                    text_content += f"\n\n--- Dữ liệu từ file tài liệu: {f.name} ---\n{decoded_text}\n--- Hết file ---"
                except Exception as e:
                    logger.error("Lỗi đọc file: %s", str(e))
            else:
                text_content += f"\n\n[Hệ thống: Có đính kèm file {f.name} nhưng định dạng này AI chưa hỗ trợ đọc trực tiếp]"

    if has_images:
        user_content = [{"type": "text", "text": text_content}] + image_contents
    else:
        user_content = text_content

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "You are a friendly and versatile AI assistant. You can chat about any topic, answer general knowledge questions, and also help users operate their Odoo ERP system."},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.5 
    }

    try:
        res = await call_openai(payload)
        data = res.json()
        logger.info(f"Dữ liệu nhận từ Odoo: {data}")

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