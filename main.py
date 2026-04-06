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
@app.post("/chat")
async def chat(request: Request):
    try:
        # 1. Lấy dữ liệu thô và log để kiểm tra
        body = await request.json()
        logger.info(f"Dữ liệu nhận từ Odoo: {body}")

        # 2. Xử lý trường hợp Odoo bọc trong 'params' (JSON-RPC)
        # Nếu chat từ UI Odoo, dữ liệu thường nằm trong body['params']
        data = body.get('params', body)

        # 3. Lấy nội dung tin nhắn (hỗ trợ nhiều tên field khác nhau)
        prompt_text = data.get("message") or data.get("question") or ""
        files = data.get("files") or [] # Nếu không có file thì để danh sách rỗng

        # 4. Kiểm tra điều kiện tối thiểu
        if not prompt_text and not files:
            return JSONResponse(
                status_code=400, 
                content={"reply": "Bạn chưa nhập nội dung tin nhắn."}
            )

        # 5. Kiểm tra API Key (Đảm bảo đã load từ Environment Variables)
        if not OPENAI_API_KEY:
            logger.error("Chưa cấu hình OPENAI_API_KEY")
            return JSONResponse(status_code=500, content={"reply": "Server chưa cấu hình API Key"})

        # 6. Chuẩn bị nội dung gửi OpenAI
        # Vì bạn chỉ chat text, logic này sẽ bỏ qua phần image_url
        text_content = prompt_text
        
        # Nếu có file (trường hợp sau này bạn đính kèm)
        if files:
            for f in files:
                # Nếu f là object (dict), dùng f.get(), nếu là object Pydantic dùng f.type
                f_type = f.get('type', '') if isinstance(f, dict) else f.type
                f_name = f.get('name', '') if isinstance(f, dict) else f.name
                f_data = f.get('data', '') if isinstance(f, dict) else f.data
                
                if f_type.startswith("text/") or f_name.endswith(('.csv', '.txt')):
                    try:
                        import base64
                        decoded_text = base64.b64decode(f_data).decode('utf-8')
                        text_content += f"\n\n[File: {f_name}]\n{decoded_text}"
                    except:
                        pass

        # 7. Gọi OpenAI
        payload = {
            "model": OPENAI_MODEL or "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a helpful Odoo assistant."},
                {"role": "user", "content": text_content}
            ],
            "temperature": 0.7
        }

        res = await call_openai(payload)
        res_data = res.json()

        if res.status_code != 200:
            return JSONResponse(status_code=502, content={"reply": "Lỗi từ OpenAI API"})

        reply = res_data["choices"][0]["message"]["content"]
        
        # Trả về định dạng Odoo mong đợi
        return {"reply": reply}

    except Exception as e:
        logger.exception("Lỗi xử lý chat")
        return JSONResponse(status_code=500, content={"reply": f"Lỗi nội bộ: {str(e)}"})