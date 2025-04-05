#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import sys
import uuid
import json
import hashlib
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends, HTTPException, Cookie, status
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic
from pydantic import BaseModel
from dotenv import load_dotenv
import markdown2
import jwt
from starlette.middleware.sessions import SessionMiddleware
from datetime import datetime, timedelta

# 将项目根目录添加到Python路径
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.append(str(ROOT_DIR))

# 确保终端显示中文
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from src.app.chat_bean import ChatMessage
from src.agents.deepresearch_agent import DeepresearchAgent
from src.tools.distribution.email_sender import EmailSender
from src.app.client_user_manager import client_auth_router, initialize_client_user_manager
from src.database.mysql.schemas.chat_schema import CHAT_SCHEMA, init_chat_default_data
from src.database.mysql.mysql_base import MySQLBase
from src.utils.log_utils import setup_logging
from src.tools.crawler.crawler_config import crawler_config_manager
from src.session.session_manager import SessionManager
from src.utils.json_parser import str2Json

# 加载环境变量
load_dotenv()

# 设置日志
logger = setup_logging(app_name="app")

# 确保必要的目录存在
from src.utils.file_utils import ensure_app_directories
ensure_app_directories()

# 创建FastAPI应用
app = FastAPI(title="深度研究助手 - 对客版")

# 添加会话中间件
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# 创建模板引擎
templates = Jinja2Templates(directory="templates")

# 创建数据库管理器实例
db_manager = crawler_config_manager
# 创建MySQL连接
mysql_base = MySQLBase()
mysql_connection = mysql_base.connection
# 初始化客户端用户管理器
initialize_client_user_manager(mysql_connection, SECRET_KEY)

# 初始化对话系统数据库表结构
def init_dialog_database():
    try:
        connection = mysql_connection
        cursor = connection.cursor()
        
        # 创建对话系统相关的表
        for table_name, table_sql in CHAT_SCHEMA.items():
            cursor.execute(table_sql)
            logger.info(f"对话系统表 {table_name} 初始化成功")
        
        # 初始化默认数据
        init_chat_default_data(connection)
        
        connection.commit()
        logger.info("对话系统数据库初始化成功")
    except Exception as e:
        logger.error(f"初始化对话系统数据库失败: {str(e)}")

# 初始化对话系统数据库
init_dialog_database()

# 包含客户端用户认证路由
app.include_router(client_auth_router)

# 全局代理实例
agent_instances = {}
# 创建邮件发送工具实例
email_sender = EmailSender()
# 任务状态追踪
active_streams = {}
# 实例化会话管理器
session_manager = SessionManager()

def get_current_user(request: Request):
    """
    从JWT令牌获取当前用户信息，用于模板渲染
    
    Args:
        request: 请求对象
    
    Returns:
        Dict: 用户信息，包含username和user_id；未登录时返回None
    """
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        username = payload.get("username")
        phone = payload.get("phone")
        user_id = payload.get("user_id")
        email = payload.get("email")
        if username is None or user_id is None:
            return None
        return {"username": username, "phone": phone, "user_id": user_id, "email": email}
    except jwt.PyJWTError:
        return None

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

# 请求模型
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    platforms: List[str] = ["web_site", "github", "arxiv", "weibo", "weixin", "twitter"]
    email: Optional[str] = None

@app.get("/api/chat/history")
async def get_chat_history(request: Request):
    """
    获取当前用户的所有聊天历史会话
    """
    # 获取当前用户
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user_id = user["user_id"]
    
    try:
        # 从数据库获取用户会话列表
        sessions = session_manager.list_sessions(user_id=user_id, limit=50)
        
        # 获取每个会话的第一条用户消息
        result = []
        for session in sessions:
            session_id = session.get('id')
            
            # 为每个会话查询消息数量和第一条用户消息
            with MySQLBase().connection.cursor() as cursor:
                # 获取消息总数
                cursor.execute(
                    "SELECT COUNT(*) as count FROM messages WHERE session_id = %s",
                    (session_id,)
                )
                count_result = cursor.fetchone()
                message_count = count_result.get('count', 0) if count_result else 0
                
                # 获取第一条用户消息
                cursor.execute(
                    "SELECT content FROM messages WHERE session_id = %s AND role = 'user' ORDER BY created_at ASC LIMIT 1",
                    (session_id,)
                )
                first_message_result = cursor.fetchone()
                first_message = first_message_result.get('content') if first_message_result else None
            
            result.append({
                "id": session_id,
                "title": session.get("title", "未命名会话"),
                "created_at": session.get("created_at").isoformat() if session.get("created_at") else None,
                "updated_at": session.get("updated_at").isoformat() if session.get("updated_at") else None,
                "message_count": message_count,
                "first_message": first_message
            })
        
        return result
    except Exception as e:
        logger.error(f"获取聊天历史列表失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取聊天历史失败: {str(e)}")

@app.get("/api/chat/history/{session_id}")
async def get_session_history(session_id: str, request: Request):
    """
    获取特定会话的历史消息
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"}
        )
    user_id = user["user_id"]
    try:
        # 先检查会话是否存在且属于当前用户
        session = session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        if session.get('user_id') != user_id:
            raise HTTPException(status_code=403, detail="无权访问此会话")
        
        # 从数据库获取会话历史记录
        with MySQLBase().connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, role, content, created_at FROM messages WHERE session_id = %s ORDER BY created_at ASC",
                (session_id,)
            )
            messages = cursor.fetchall()
        
        # 格式化消息
        formatted_messages = [{
            "id": msg.get('id'),
            "role": msg.get('role'),
            "content": msg.get('content'),
            "timestamp": msg.get('created_at').isoformat() if msg.get('created_at') else None
        } for msg in messages]
        
        return {
            "id": session_id,
            "title": session.get('title', "未命名会话"),
            "created_at": session.get('created_at').isoformat() if session.get('created_at') else None,
            "updated_at": session.get('updated_at').isoformat() if session.get('updated_at') else None,
            "user_id": user_id,
            "messages": formatted_messages
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话历史记录失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取会话历史记录失败: {str(e)}")

@app.get("/api/chat")
async def chat_stream(request: Request):
    """
    SSE聊天接口 - 流式响应，与chat_sse功能相同但路径不同
    """
    stream_id = request.query_params.get("stream_id")
    if not stream_id:
        stream_id = str(uuid.uuid4())
    
    message = request.query_params.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="必须提供message参数")
    
    session_id = request.query_params.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
    
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return StreamingResponse(
        process_chat_request(stream_id, user, session_id, message),
        media_type="text/event-stream"
    )

@app.post("/api/abort")
async def abort_stream(request: Request):
    """
    中止指定的SSE流并重置用户的速率限制
    """
    data = await request.json()
    stream_id = data.get("stream_id")
    
    if not stream_id or stream_id not in active_streams:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid stream_id"}
        )

    session_id = active_streams[stream_id].get("session_id")
    active_streams[stream_id]["active"] = False
    logger.info(f"手动中止流 [stream_id={stream_id}]")
    
    # 释放资源：如果使用了信号量来限制请求速率，则释放该信号量
    try:
        # 尝试获取关联的agent实例
        if session_id and session_id in agent_instances:
            agent = agent_instances[session_id]
            # 如果agent有信号量属性，则释放它
            if hasattr(agent, 'semaphore') and agent.semaphore:
                agent.semaphore.release()
                logger.info(f"释放用户信号量资源 [session_id={session_id}]")
    except Exception as e:
        logger.error(f"释放信号量资源失败: {str(e)}")
    
    return JSONResponse(
        content={"status": "success", "message": "Stream aborted"}
    )

async def process_chat_request(stream_id: str, user: Dict[str, Any], session_id: str, message: str):
    """处理聊天请求的通用函数"""
    active_streams[stream_id] = {
        "active": True,
        "session_id": session_id,
        "message": message
    }
    agent = get_agent(session_id)
    full_response = ""
    try:
        async for chunk in agent.process_stream(ChatMessage(message=message)):
            if not active_streams.get(stream_id, {}).get("active", False):
                logger.info(f"流已被客户端中止 [stream_id={stream_id}]")
                break
                
            if chunk:
                chunk_type = chunk.get("type", "")
                if chunk_type == "research_process":
                    yield f"event: status\ndata: {json.dumps(chunk)}\n\n"
                if chunk_type == "content":
                    full_response += chunk.get("content", "")
                    yield f"event: content\ndata: {json.dumps(chunk)}\n\n"
        yield f"event: complete\ndata: {json.dumps({'type': 'complete', 'content': session_id})}\n\n"
        try:
            await send_email_with_results(message, full_response, user.get("email"))
        except Exception as e:
            logger.error(f"发送邮件失败: {str(e)}", exc_info=True)
    except Exception as e:
        error_msg = f"处理请求时出错: {str(e)}"
        logger.error(error_msg, exc_info=True)
        yield f"event: error\ndata: {json.dumps({'event': 'error', 'message': error_msg})}\n\n"
    finally:
        if stream_id in active_streams:
            active_streams[stream_id]["active"] = False
            logger.info(f"流处理完成 [stream_id={stream_id}]")

async def send_email_with_results(query: str, response: str, email: str = None):
    """
    发送邮件给用户，包含研究结果
    
    Args:
        query: 用户查询
        response: 完整响应内容
        email: 用户邮箱地址
    """
    if not email:
        return
    logger.info(f"准备发送邮件到: {email} 和管理员邮箱")
    try:
        subject = f"深度研究结果: {query[:30]}{'...' if len(query) > 30 else ''}"
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
            <p>感谢您使用深度研究助手!</p>
        </body>
        </html>
        """
        
        # 传递用户邮箱作为额外收件人
        # EMAIL_RECIPIENT 环境变量已在 EmailSender 类初始化时处理，无需重复添加
        await email_sender.send_email(
            subject=subject,
            body=html_content,
            is_html=True,
            additional_recipients=[email]  # 用户邮箱作为额外收件人
        )
        
        logger.info(f"邮件已成功发送到: {email} 和管理员邮箱")
        return True
    except Exception as e:
        logger.error(f"发送邮件失败: {str(e)}")
        return False

@app.get("/")
async def index(request: Request):
    """
    首页
    """
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("app/index.html", {"request": request, "user": user})

@app.get("/login")
async def login_page(request: Request):
    """
    登录页面
    """
    return templates.TemplateResponse("app/login.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    
    print("\n深度研究助手 - 对客版\n")
    print("启动Web服务器...")
    print("访问 http://127.0.0.1:8000/ 开始使用")
    
    uvicorn.run(app, host="127.0.0.1", port=8000)