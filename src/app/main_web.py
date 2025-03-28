#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import sys
import uuid
import json
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv
import markdown2

# 将项目根目录添加到Python路径
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.append(str(ROOT_DIR))

# 确保终端显示中文
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from src.app.response import ChatMessage
from src.agents.deepresearch_agent import DeepresearchAgent
from src.tools.distribution.email_sender import EmailSender

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
# 任务状态追踪
active_streams = {}

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

@app.get("/api/chat")
async def chat_sse(request: Request):
    """
    SSE聊天接口 - GET请求版本，为了支持EventSource
    """
    stream_id = request.query_params.get("stream_id")
    if not stream_id:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing stream_id parameter"}
        )
    
    message = request.query_params.get("message")
    if not message:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing message parameter"}
        )
    
    session_id = request.query_params.get("session_id", str(uuid.uuid4()))
    email = request.query_params.get("email")
    
    # 记录活动任务状态
    active_streams[stream_id] = {
        "active": True,
        "session_id": session_id,
        "message": message,
        "email": email
    }
    
    # 获取或创建代理实例
    agent = get_agent(session_id)
    
    async def generate():
        full_response = ""
        sources = []
        
        try:
            logger.info(f"开始处理流式请求 [stream_id={stream_id}, session_id={session_id}]")
            
            # 发送初始事件
            event_type = "status"
            yield f"event: {event_type}\ndata: {json.dumps({'content': '开始处理您的查询...', 'phase': 'init'})}\n\n"
            
            # 处理流式响应
            async for chunk in agent.process_stream(ChatMessage(message=message)):
                # 检查流是否已被客户端中止
                if not active_streams.get(stream_id, {}).get("active", False):
                    logger.info(f"流已被客户端中止 [stream_id={stream_id}]")
                    break
                
                event_type = chunk.get("type", "content")
                
                if event_type == "content":
                    full_response += chunk.get("content", "")
                elif event_type == "sources" and "content" in chunk:
                    sources = chunk["content"]
                
                yield f"event: {event_type}\ndata: {json.dumps(chunk)}\n\n"
            
            # 发送完成事件
            if active_streams.get(stream_id, {}).get("active", False):
                yield f"event: complete\ndata: {json.dumps({'content': '处理完成'})}\n\n"
                
                # 如果有邮箱地址，则发送邮件
                if email:
                    try:
                        await send_email_with_results(message, full_response, email, sources)
                        yield f"event: status\ndata: {json.dumps({'content': '已将结果发送到您的邮箱', 'phase': 'email_sent'})}\n\n"
                    except Exception as e:
                        logger.error(f"发送邮件失败: {str(e)}", exc_info=True)
                        yield f"event: status\ndata: {json.dumps({'content': f'发送邮件失败: {str(e)}', 'phase': 'email_error'})}\n\n"
        
        except Exception as e:
            logger.error(f"处理请求时出错: {str(e)}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'content': str(e)})}\n\n"
        
        finally:
            # 清理流状态
            if stream_id in active_streams:
                active_streams[stream_id]["active"] = False
                logger.info(f"流处理完成 [stream_id={stream_id}]")
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/api/abort")
async def abort_stream(request: Request):
    """
    中止指定的SSE流
    """
    data = await request.json()
    stream_id = data.get("stream_id")
    
    if not stream_id or stream_id not in active_streams:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid stream_id"}
        )
    
    # 标记流为非活动
    active_streams[stream_id]["active"] = False
    logger.info(f"手动中止流 [stream_id={stream_id}]")
    
    return JSONResponse(
        content={"status": "success", "message": "Stream aborted"}
    )

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    聊天接口 - POST请求版本，兼容非SSE客户端
    """
    print(f"收到聊天请求: {request.message}")
    agent = get_agent(request.session_id)
    
    async def generate():
        # 使用带有进度更新的流式处理
        try:
            # 初始状态事件
            yield f"{json.dumps({'type': 'status', 'content': '开始处理您的请求...', 'phase': 'init'})}\n"
            
            full_response = ""
            
            # 使用增强的流式处理方法
            async for chunk in agent.process_stream(ChatMessage(message=request.message)):
                # 根据不同类型的chunk进行处理
                if isinstance(chunk, dict):
                    # 如果是内容类型，则累积完整响应
                    if chunk.get("type") == "content":
                        full_response += chunk["content"]
                    
                    # 转换为换行分隔的JSON
                    yield f"{json.dumps(chunk)}\n"
                else:
                    # 对于字符串类型，作为content处理
                    content_chunk = {"type": "content", "content": chunk}
                    full_response += chunk
                    yield f"{json.dumps(content_chunk)}\n"
            
            # 完成事件
            yield f"{json.dumps({'type': 'complete', 'content': '处理完成'})}\n"
            
            # 发送邮件（如果提供了邮箱地址）
            if request.email:
                await send_email_with_results(request.message, full_response, request.email)
                yield f"{json.dumps({'type': 'status', 'content': f'结果已发送至邮箱: {request.email}', 'phase': 'email_sent'})}\n"
        
        except Exception as e:
            error_msg = f"处理请求时出错: {str(e)}"
            logger.error(error_msg, exc_info=True)
            yield f"{json.dumps({'type': 'error', 'content': error_msg})}\n"
    
    return StreamingResponse(generate(), media_type="application/json")

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket聊天
    
    Args:
        websocket: WebSocket连接
    """
    await websocket.accept()
    
    try:
        # 获取初始连接参数
        connection_data = await websocket.receive_json()
        session_id = connection_data.get("session_id", "")
        
        await websocket.send_json({
            "type": "system",
            "content": "WebSocket连接已建立"
        })
        
        agent = get_agent(session_id)
        
        # 循环处理消息
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            request_id = data.get("request_id", str(uuid.uuid4()))
            
            if not message:
                await websocket.send_json({
                    "type": "error",
                    "content": "消息不能为空",
                    "request_id": request_id
                })
                continue
            
            # 发送初始状态更新
            await websocket.send_json({
                "type": "status",
                "content": "开始处理您的请求...",
                "phase": "init",
                "request_id": request_id
            })
            
            full_response = ""
            found_sources = []
            current_phase = "init"
            
            try:
                # 流式处理响应
                async for chunk in agent.process_stream(ChatMessage(message=message)):
                    # 处理不同类型的chunk
                    if isinstance(chunk, dict):
                        chunk_type = chunk.get("type", "content")
                        
                        # 追踪完整响应
                        if chunk_type == "content" and "content" in chunk:
                            full_response += chunk["content"]
                        
                        # 更新当前阶段
                        if chunk_type == "status" and "phase" in chunk:
                            current_phase = chunk["phase"]
                        
                        # 收集源引用
                        if chunk_type == "sources" and "content" in chunk and isinstance(chunk["content"], list):
                            found_sources = chunk["content"]
                        
                        # 添加请求ID并发送
                        chunk["request_id"] = request_id
                        await websocket.send_json(chunk)
                    else:
                        # 字符串直接作为内容发送
                        content_chunk = {
                            "type": "content",
                            "content": chunk,
                            "request_id": request_id
                        }
                        full_response += chunk
                        await websocket.send_json(content_chunk)
                
                # 确保完成阶段被标记
                if current_phase != "complete":
                    await websocket.send_json({
                        "type": "status",
                        "content": "处理完成",
                        "phase": "complete",
                        "request_id": request_id
                    })
                
                # 发送完成事件
                await websocket.send_json({
                    "type": "complete",
                    "content": "处理完成",
                    "request_id": request_id
                })
                
                # 处理邮件发送
                email = data.get("email")
                if email:
                    await send_email_with_results(message, full_response, email, found_sources)
                    await websocket.send_json({
                        "type": "status",
                        "content": f"结果已发送至邮箱: {email}",
                        "phase": "email_sent",
                        "request_id": request_id
                    })
            
            except Exception as e:
                error_msg = f"处理请求时出错: {str(e)}"
                logger.error(error_msg, exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "content": error_msg,
                    "request_id": request_id
                })
    
    except WebSocketDisconnect:
        logger.info("WebSocket连接断开")
    except Exception as e:
        logger.error(f"WebSocket错误: {str(e)}", exc_info=True)

async def send_email_with_results(query: str, response: str, email: str = None, sources=None):
    """
    发送邮件给用户，包含研究结果
    
    Args:
        query: 用户查询
        response: 完整响应内容
        email: 用户邮箱地址
        sources: 引用的来源列表
    """
    if not email:
        return
    
    logger.info(f"准备发送邮件到: {email}")
    
    try:
        # 准备邮件主题和内容
        subject = f"深度研究结果: {query[:30]}{'...' if len(query) > 30 else ''}"
        
        # 添加HTML格式内容
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
                h1 {{ color: #1a73e8; margin-bottom: 20px; }}
                h2 {{ color: #188038; margin-top: 30px; margin-bottom: 15px; }}
                p {{ margin-bottom: 15px; }}
                .query {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 25px; border-left: 4px solid #1a73e8; }}
                .response {{ background: #ffffff; padding: 20px; border-radius: 5px; border: 1px solid #dadce0; }}
                .sources {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #dadce0; }}
                .source-item {{ margin-bottom: 10px; }}
                a {{ color: #1a73e8; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <h1>深度研究结果</h1>
            <div class="query">
                <strong>您的查询:</strong> {query}
            </div>
            <h2>研究结果:</h2>
            <div class="response">
                {markdown2.markdown(response)}
            </div>
        """
        
        # 如果有来源信息，添加到邮件中
        if sources and isinstance(sources, list) and len(sources) > 0:
            html_content += """
            <div class="sources">
                <h2>参考来源:</h2>
                <ul>
            """
            
            for idx, source in enumerate(sources):
                source_url = source.get("url", "#")
                source_title = source.get("title", f"来源 {idx+1}")
                html_content += f"""
                <li class="source-item">
                    <a href="{source_url}" target="_blank">{source_title}</a>
                </li>
                """
            
            html_content += """
                </ul>
            </div>
            """
        
        html_content += """
            <p>感谢您使用深度研究助手!</p>
        </body>
        </html>
        """
        
        # 发送邮件
        await email_sender.send_email(
            recipient=email,
            subject=subject,
            html_content=html_content
        )
        
        logger.info(f"邮件已成功发送到: {email}")
        return True
    
    except Exception as e:
        logger.error(f"发送邮件失败: {str(e)}")
        return False

if __name__ == "__main__":
    import uvicorn
    
    print("\n深度研究助手 - Web版\n")
    print("启动Web服务器...")
    print("访问 http://127.0.0.1:8000/ 开始使用")
    
    uvicorn.run(app, host="127.0.0.1", port=8000)