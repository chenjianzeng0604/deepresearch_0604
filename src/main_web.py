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
import markdown

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
from src.distribution.email_sender import EmailSender

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

# 创建FastAPI应用
app = FastAPI(title="深度研究助手 - Web版")

# 创建模板引擎
templates = Jinja2Templates(directory="templates")

# 请求模型
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    platforms: List[str] = ["web_site", "github", "arxiv", "weibo", "weixin", "twitter"]
    email: Optional[str] = None

# 全局代理实例
agent_instances = {}
# 创建邮件发送工具实例
email_sender = EmailSender()

def get_agent(session_id: str) -> DeepresearchAgent:
    """
    获取或创建代理实例
    
    Args:
        session_id: 会话ID
        
    Returns:
        DeepresearchAgent: 代理实例
    """
    if session_id not in agent_instances:
        agent_instances[session_id] = DeepresearchAgent(session_id=session_id)
    
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
    
    message = ChatMessage(
        session_id=session_id,
        message=request.message,
        metadata={"platforms": ["web_site", "search", "github", "arxiv", "weibo", "weixin", "twitter"]}
    )
    
    full_response = ""
    
    async def generate():
        
        nonlocal full_response
        
        research_results = await agent._research(message)
        
        async for chunk in agent._generate_response_stream(message, research_results):
            if isinstance(chunk, dict):
                yield f"data: {json.dumps(chunk)}\n\n"
            else:
                full_response += chunk
                yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
        
        await send_email_with_results(message.message, full_response)
    
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
            data = await websocket.receive_text()
            request_data = json.loads(data)
            
            session_id = request_data.get("session_id") or str(uuid.uuid4())
            agent = get_agent(session_id)
            
            message = ChatMessage(
                session_id=session_id,
                message=request_data.get("message", ""),
                metadata={"platforms": request_data.get("platforms", ["web_site", "github", "arxiv", "weibo", "weixin", "twitter"])}
            )
            
            full_response = ""
            research_results = None
            
            research_results = await agent._research(message)
            
            async for chunk in agent._generate_response_stream(message, research_results):
                if isinstance(chunk, dict):
                    await websocket.send_json(chunk)
                else:
                    full_response += chunk
                    await websocket.send_json({"type": "content", "content": chunk})
            
            await websocket.send_json({"type": "done"})
            await send_email_with_results(message.message, full_response)
            
    except WebSocketDisconnect:
        logger.info("WebSocket连接已断开")
    except Exception as e:
        logger.error(f"WebSocket聊天出错: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass

async def send_email_with_results(query: str, response: str):
    """
    发送邮件给用户，包含研究结果
    
    Args:
        query: 用户查询
        response: 完整响应内容
    """
    try:
        subject = f"深度研究结果: {query[:50]}{'...' if len(query) > 50 else ''}"
        extensions = [
            'fenced_code',  # 代码块
            'tables',       # 表格
            'nl2br'         # 换行转 <br>
        ]
        await email_sender.send_email(
            subject=subject,
            body=f"<!DOCTYPE html><html><body>{markdown.markdown(response, extensions=extensions, safe_mode=True)}</body></html>",
            is_html=True
        )
    except Exception as e:
        logger.error(f"发送邮件失败: {str(e)}", exc_info=True)

if __name__ == "__main__":
    import uvicorn
    
    print("\n深度研究助手 - Web版\n")
    print("启动Web服务器...")
    print("访问 http://127.0.0.1:8000/ 开始使用")
    
    uvicorn.run(app, host="127.0.0.1", port=8000)