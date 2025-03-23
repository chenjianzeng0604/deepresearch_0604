#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import asyncio
import logging
import sys
import uuid
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, AsyncGenerator
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

# 将项目根目录添加到Python路径
ROOT_DIR = Path(__file__).parent.parent
sys.path.append(str(ROOT_DIR))

# 确保终端显示中文
import io
import locale
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from src.models.config import AppConfig
from src.models.response import ChatMessage
from src.agents.deepresearch_agent import DeepresearchAgent

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join("data", "logs", "app.log"), encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# 确保必要的目录存在
os.makedirs("data/logs", exist_ok=True)
os.makedirs("data/reports", exist_ok=True)
os.makedirs("data/reports/images", exist_ok=True)
os.makedirs("data/knowledge_base", exist_ok=True)

# 创建templates目录
os.makedirs("templates", exist_ok=True)

def load_config() -> AppConfig:
    """
    加载应用配置
    
    Returns:
        AppConfig: 应用配置
    """
    config_data = {
        "llm": {
            "api_key": os.getenv("OPENAI_API_KEY", ""),
            "api_base": os.getenv("OPENAI_API_BASE", ""),
            "model": os.getenv("LLM_MODEL", "deepseek-r1"),
            "temperature": float(os.getenv("LLM_TEMPERATURE", "0.7")),
            "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "4096")),
            "use_tool_model": os.getenv("LLM_USE_TOOL_MODEL", "qwen2.5-72b-instruct")
        },
        "search": {
            "api_key": os.getenv("SEARCH_API_KEY", ""),
            "engine": os.getenv("SEARCH_ENGINE", "google"),
            "enabled": True
        },
        "distribution": {
            "wechat_official_account": {
                "enabled": os.getenv("WECHAT_OA_ENABLED", "false").lower() == "true",
                "api_url": os.getenv("WECHAT_API_URL", ""),
                "app_id": os.getenv("WECHAT_OA_APP_ID", ""),
                "app_secret": os.getenv("WECHAT_OA_APP_SECRET", "")
            }
        }
    }
    return AppConfig(**config_data)

# 创建FastAPI应用
app = FastAPI(title="深度研究助手 - Web版")

# 创建模板引擎
templates = Jinja2Templates(directory="templates")

# 请求模型
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    platforms: List[str] = ["web_site", "github", "arxiv", "weibo", "weixin", "twitter"]

# 全局代理实例
agent_instances = {}

def get_agent(session_id: str) -> DeepresearchAgent:
    """
    获取或创建代理实例
    
    Args:
        session_id: 会话ID
        
    Returns:
        DeepresearchAgent: 代理实例
    """
    if session_id not in agent_instances:
        config = load_config()
        agent_instances[session_id] = DeepresearchAgent(session_id=session_id, config=config)
    
    return agent_instances[session_id]

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    首页
    """
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    聊天API
    
    Args:
        request: 聊天请求
        
    Returns:
        StreamingResponse: 流式响应
    """
    session_id = request.session_id or str(uuid.uuid4())
    agent = get_agent(session_id)
    
    # 创建聊天消息
    message = ChatMessage(
        session_id=session_id,
        message=request.message,
        metadata={"platforms": ["web_site", "search", "github", "arxiv", "weibo", "weixin", "twitter"]}
    )
    
    async def generate():
        async for chunk in agent.process_stream(message):
            if isinstance(chunk, dict):
                yield f"data: {json.dumps(chunk)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket聊天
    
    Args:
        websocket: WebSocket连接
    """
    await websocket.accept()
    
    try:
        while True:
            # 接收消息
            data = await websocket.receive_text()
            request_data = json.loads(data)
            
            # 获取会话ID
            session_id = request_data.get("session_id") or str(uuid.uuid4())
            agent = get_agent(session_id)
            
            # 创建聊天消息
            message = ChatMessage(
                session_id=session_id,
                message=request_data.get("message", ""),
                metadata={"platforms": request_data.get("platforms", ["web_site", "github", "arxiv", "weibo", "weixin", "twitter"])}
            )
            
            # 发送响应
            async for chunk in agent.process_stream(message):
                if isinstance(chunk, dict):
                    await websocket.send_json(chunk)
                else:
                    await websocket.send_json({"type": "content", "content": chunk})
            
            # 发送完成标记
            await websocket.send_json({"type": "done"})
            
    except WebSocketDisconnect:
        logger.info("WebSocket连接已断开")
    except Exception as e:
        logger.error(f"WebSocket聊天出错: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    
    print("\n深度研究助手 - Web版\n")
    print("启动Web服务器...")
    print("访问 http://127.0.0.1:8000/ 开始使用")
    
    uvicorn.run(app, host="127.0.0.1", port=8000)