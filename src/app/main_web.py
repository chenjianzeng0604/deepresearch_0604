#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import sys
import uuid
import json
import hashlib
from pathlib import Path
from typing import List, Optional, Dict
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends, HTTPException, Cookie, status
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from dotenv import load_dotenv
import markdown2
import jwt
from starlette.middleware.sessions import SessionMiddleware
import random
import string
from datetime import datetime, timedelta
import time
import inspect
import asyncio

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
from src.admin.crawler_config_manager import CrawlerConfigManager
from src.app.client_user_manager import client_auth_router, initialize_client_user_manager
from src.database.mysql.schemas.chat_schema import CHAT_SCHEMA, init_chat_default_data
from src.database.mysql.mysql_base import MySQLBase
from src.utils.log_utils import setup_logging

# 加载环境变量
load_dotenv()

# 设置日志
logger = setup_logging(app_name="app")

# 确保必要的目录存在
from src.utils.file_utils import ensure_app_directories
ensure_app_directories()

# 创建FastAPI应用
app = FastAPI(title="深度研究助手 - Web版")

# 添加会话中间件
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "deepresearch_default_secret_key")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# 创建模板引擎
templates = Jinja2Templates(directory="templates")

# 创建数据库管理器实例
db_manager = CrawlerConfigManager()
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

# 会话历史存储
chat_history = {}  # 格式: {session_id: {"messages": [], "created_at": timestamp, "updated_at": timestamp, "title": "", "user_id": user_id}}

# JWT工具函数
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")
    return encoded_jwt

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
        username = payload.get("sub")
        user_id = payload.get("user_id")
        if username is None or user_id is None:
            return None
        return {"username": username, "user_id": user_id}
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

# 生成短信验证码
def generate_verification_code():
    """生成6位数字验证码"""
    return ''.join(random.choices(string.digits, k=6))

# 请求模型
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    platforms: List[str] = ["web_site", "github", "arxiv", "weibo", "weixin", "twitter"]
    email: Optional[str] = None

# 用于保护接口的依赖函数
async def get_current_user_from_token(request: Request):
    """
    从JWT令牌获取当前用户信息，用于API接口保护
    
    Args:
        request: 请求对象
    
    Returns:
        Dict: 用户信息，包含username和user_id
    
    Raises:
        HTTPException: 当令牌无效或不存在时抛出401未授权异常
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未授权访问",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        username = payload.get("sub")
        user_id = payload.get("user_id")
        if username is None or user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的凭证",
                headers={"WWW-Authenticate": "Bearer"}
            )
        return {"username": username, "user_id": user_id}
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的凭证",
            headers={"WWW-Authenticate": "Bearer"}
        )

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
    
    # 筛选当前用户的会话
    user_sessions = {
        session_id: session_data 
        for session_id, session_data in chat_history.items()
        if session_data.get("user_id") == user_id
    }
    
    # 按更新时间倒序排序
    sorted_history = [
        {
            "id": session_id,
            "title": session_data.get("title", "未命名会话"),
            "created_at": session_data.get("created_at"),
            "updated_at": session_data.get("updated_at"),
            "message_count": len(session_data.get("messages", [])),
            "first_message": next((msg.get("content") for msg in session_data.get("messages", []) 
                               if msg.get("role") == "user"), None)
        }
        for session_id, session_data in user_sessions.items()
    ]
    
    # 按更新时间倒序排序
    sorted_history.sort(key=lambda x: x["updated_at"], reverse=True)
    
    return sorted_history

@app.get("/api/chat/history/{session_id}")
async def get_session_history(session_id: str, request: Request):
    """
    获取特定会话的历史消息
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
    
    if session_id not in chat_history:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 检查会话所有权
    session_data = chat_history[session_id]
    if session_data.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="无权访问此会话")
    
    return chat_history[session_id]

@app.delete("/api/chat/history/{session_id}")
async def delete_session_history(session_id: str, request: Request):
    """
    删除特定会话的历史记录
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
    
    if session_id not in chat_history:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 检查会话所有权
    session_data = chat_history[session_id]
    if session_data.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="无权删除此会话")
    
    del chat_history[session_id]
    return {"success": True, "message": "会话已删除"}

@app.get("/api/chat")
async def chat_sse(request: Request):
    """
    SSE聊天接口 - GET请求版本，为了支持EventSource
    """
    stream_id = request.query_params.get("stream_id")
    if not stream_id:
        stream_id = str(uuid.uuid4())
    
    message = request.query_params.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="必须提供message参数")
    
    session_id = request.query_params.get("session_id")
    platforms_str = request.query_params.get("platforms", "web_site,github,arxiv,weibo,weixin,twitter")
    platforms = platforms_str.split(",")
    email = request.query_params.get("email")
    
    # 获取当前用户
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user_id = user["user_id"]
    
    # 创建新会话或获取现有会话
    if not session_id:
        session_id = str(uuid.uuid4())
        chat_history[session_id] = {
            "messages": [],
            "created_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat(),
            "title": "",
            "user_id": user_id
        }
    elif session_id not in chat_history:
        chat_history[session_id] = {
            "messages": [],
            "created_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat(),
            "title": "",
            "user_id": user_id
        }
    else:
        # 验证会话所有权
        if chat_history[session_id].get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="无权访问此会话")
    
    # 保存用户消息到历史
    chat_history[session_id]["messages"].append({
        "role": "user",
        "content": message,
        "timestamp": datetime.datetime.now().isoformat()
    })
    
    # 如果是首次消息，使用它作为会话标题
    if len(chat_history[session_id]["messages"]) == 1:
        # 截取前30个字符作为标题
        title = message[:30] + ("..." if len(message) > 30 else "")
        chat_history[session_id]["title"] = title
    
    # 更新会话最后修改时间
    chat_history[session_id]["updated_at"] = datetime.datetime.now().isoformat()
    
    # 创建响应流
    return StreamingResponse(
        process_chat_request(stream_id, session_id, message, platforms, email),
        media_type="text/event-stream"
    )

@app.get("/api/chat/stream")
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
    platforms_str = request.query_params.get("platforms", "web_site,github,arxiv,weibo,weixin,twitter")
    platforms = platforms_str.split(",")
    email = request.query_params.get("email")
    
    # 获取当前用户
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user_id = user["user_id"]
    
    # 创建新会话或获取现有会话
    if not session_id:
        session_id = str(uuid.uuid4())
        chat_history[session_id] = {
            "messages": [],
            "created_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat(),
            "title": "",
            "user_id": user_id
        }
    elif session_id not in chat_history:
        chat_history[session_id] = {
            "messages": [],
            "created_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat(),
            "title": "",
            "user_id": user_id
        }
    else:
        # 验证会话所有权
        if chat_history[session_id].get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="无权访问此会话")
    
    # 保存用户消息到历史
    chat_history[session_id]["messages"].append({
        "role": "user",
        "content": message,
        "timestamp": datetime.datetime.now().isoformat()
    })
    
    # 如果是首次消息，使用它作为会话标题
    if len(chat_history[session_id]["messages"]) == 1:
        # 截取前30个字符作为标题
        title = message[:30] + ("..." if len(message) > 30 else "")
        chat_history[session_id]["title"] = title
    
    # 更新会话最后修改时间
    chat_history[session_id]["updated_at"] = datetime.datetime.now().isoformat()
    
    # 创建响应流
    return StreamingResponse(
        process_chat_request(stream_id, session_id, message, platforms, email),
        media_type="text/event-stream"
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

async def process_chat_request(stream_id: str, session_id: str, message: str, platforms: List[str], email: str = None):
    """处理聊天请求的通用函数"""
    # 记录活动任务状态
    active_streams[stream_id] = {
        "active": True,
        "session_id": session_id,
        "message": message,
        "email": email
    }
    
    # 获取或创建代理实例
    agent = get_agent(session_id)
    
    full_response = ""
    sources = []
    
    try:
        # 发送初始状态更新
        event_type = "status"
        yield f"event: {event_type}\ndata: {json.dumps({'content': '开始处理您的请求...', 'phase': 'init'})}\n\n"
        
        # 处理流式响应
        async for chunk in agent.process_stream(ChatMessage(message=message, platforms=platforms)):
            # 检查流是否已被客户端中止
            if not active_streams.get(stream_id, {}).get("active", False):
                logger.info(f"流已被客户端中止 [stream_id={stream_id}]")
                break
            
            # 处理不同类型的chunk
            if isinstance(chunk, dict):
                chunk_type = chunk.get("type", "content")
                
                # 追踪完整响应
                if chunk_type == "content" and "content" in chunk:
                    full_response += chunk["content"]
                
                # 收集源引用
                if chunk_type == "sources" and "content" in chunk and isinstance(chunk["content"], list):
                    sources = chunk["content"]
                
                # 添加请求ID并发送
                chunk["request_id"] = str(uuid.uuid4())
                yield f"event: {chunk_type}\ndata: {json.dumps(chunk)}\n\n"
            else:
                # 字符串直接作为内容发送
                content_chunk = {
                    "type": "content",
                    "content": chunk,
                    "request_id": str(uuid.uuid4())
                }
                full_response += chunk
                yield f"event: content\ndata: {json.dumps(content_chunk)}\n\n"
        
        # 保存助手回复到历史
        if full_response:
            chat_history[session_id]["messages"].append({
                "role": "assistant",
                "content": full_response,
                "timestamp": datetime.datetime.now().isoformat(),
                "sources": sources
            })
            
            # 更新会话最后修改时间
            chat_history[session_id]["updated_at"] = datetime.datetime.now().isoformat()
            
        # 确保完成阶段被标记
        yield f"event: complete\ndata: {json.dumps({'content': '处理完成'})}\n\n"
        
        # 发送邮件（如果提供了邮箱地址）
        if email:
            try:
                await send_email_with_results(message, full_response, email, sources)
                yield f"event: status\ndata: {json.dumps({'content': f'结果已发送至邮箱: {email}', 'phase': 'email_sent'})}\n\n"
            except Exception as e:
                logger.error(f"发送邮件失败: {str(e)}", exc_info=True)
                yield f"event: status\ndata: {json.dumps({'content': f'发送邮件失败: {str(e)}', 'phase': 'email_error'})}\n\n"
    
    except Exception as e:
        error_msg = f"处理请求时出错: {str(e)}"
        logger.error(error_msg, exc_info=True)
        yield f"event: error\ndata: {json.dumps({'content': error_msg})}\n\n"
    
    finally:
        # 清理流状态
        if stream_id in active_streams:
            active_streams[stream_id]["active"] = False
            logger.info(f"流处理完成 [stream_id={stream_id}]")


@app.post("/api/chat")
async def chat(chat_request: ChatRequest, request: Request):
    """
    聊天接口
    
    Args:
        chat_request: 聊天请求数据
        request: FastAPI请求对象
    
    Returns:
        Dict: 聊天响应，包含消息内容、会话ID等
    """
    # 检查用户是否已登录
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    message = chat_request.message
    session_id = chat_request.session_id
    platforms = chat_request.platforms
    email = chat_request.email
    user_id = user["user_id"]
    
    # 创建新会话或获取现有会话
    if not session_id:
        session_id = str(uuid.uuid4())
        chat_history[session_id] = {
            "messages": [],
            "created_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat(),
            "title": "",
            "user_id": user_id
        }
    elif session_id not in chat_history:
        chat_history[session_id] = {
            "messages": [],
            "created_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat(),
            "title": "",
            "user_id": user_id
        }
    else:
        # 验证会话所有权
        if chat_history[session_id].get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="无权访问此会话")
    
    # 保存用户消息到历史
    chat_history[session_id]["messages"].append({
        "role": "user",
        "content": message,
        "timestamp": datetime.datetime.now().isoformat()
    })
    
    # 如果是首次消息，使用它作为会话标题
    if len(chat_history[session_id]["messages"]) == 1:
        # 截取前30个字符作为标题
        title = message[:30] + ("..." if len(message) > 30 else "")
        chat_history[session_id]["title"] = title
    
    # 更新会话最后修改时间
    chat_history[session_id]["updated_at"] = datetime.datetime.now().isoformat()
    
    # 创建代理和获取回复
    agent = get_agent(session_id)
    try:
        response_data = await agent.process(ChatMessage(message=message, platforms=platforms))
        
        # 保存助手回复到会话历史
        content = response_data.get("content", "")
        sources = response_data.get("sources", [])
        
        if content:
            chat_history[session_id]["messages"].append({
                "role": "assistant",
                "content": content,
                "timestamp": datetime.datetime.now().isoformat(),
                "sources": sources
            })
            chat_history[session_id]["updated_at"] = datetime.datetime.now().isoformat()
        
        # 发送邮件（如果需要）
        if email:
            await send_email_with_results(message, content, email, sources)
            response_data["email_sent"] = True
        
        return response_data
    except Exception as e:
        logger.error(f"处理请求时出错: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

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
                    # 检查流是否已被客户端中止
                    if not active_streams.get(stream_id, {}).get("active", False):
                        logger.info(f"流已被客户端中止 [stream_id={stream_id}]")
                        break
                    
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
    
    print("\n深度研究助手 - Web版\n")
    print("启动Web服务器...")
    print("访问 http://127.0.0.1:8000/ 开始使用")
    
    uvicorn.run(app, host="127.0.0.1", port=8000)