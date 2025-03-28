from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class MessageRole(str, Enum):
    """消息角色枚举"""
    SYSTEM = "system"
    ASSISTANT = "assistant"
    USER = "user"


class MessageContent(BaseModel):
    """消息内容"""
    type: str = "text"  # 可以是text, image, file等
    content: str  # 文本内容或文件路径


class Message(BaseModel):
    """对话消息"""
    id: str
    role: MessageRole
    content: List[MessageContent]
    created_at: datetime = Field(default_factory=datetime.now)


class ChatMessage(BaseModel):
    """聊天消息，用于API请求和响应"""
    message: str
    files: List[str] = []
    metadata: Dict[str, Any] = {}


class ChatResponse(BaseModel):
    """聊天响应"""
    message_id: str
    response: str
    sources: List[Dict[str, Any]] = []
    created_at: datetime = Field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "message_id": self.message_id,
            "response": self.response,
            "sources": self.sources,
            "created_at": self.created_at.isoformat(),
        }
