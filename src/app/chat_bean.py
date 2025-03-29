from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import os
from dotenv import load_dotenv


# ================ Message and Chat DTOs ================

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


# ================ Configuration DTOs ================

class LLMConfig(BaseModel):
    """LLM模型配置"""
    api_key: str
    api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "deepseek-r1"
    temperature: float = 0.7
    max_tokens: int = 4096
    use_tool_model: str = "qwen2.5-72b-instruct"


class SearchConfig(BaseModel):
    """搜索配置"""
    api_key: Optional[str] = ""
    search_engine: str = "google"  # 可选值: "bing", "google", "duckduckgo"
    max_results: int = 10
    timeout: int = 30


class WeChatOfficialAccountConfig(BaseModel):
    """微信公众号配置"""
    enabled: bool = True
    api_url: str = ""
    app_id: str = ""
    app_secret: str = ""


class DistributionConfig(BaseModel):
    """分发配置"""
    wechat_official_account: WeChatOfficialAccountConfig = WeChatOfficialAccountConfig()


class AppConfig(BaseModel):
    """应用全局配置"""
    debug: bool = False
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    llm: LLMConfig
    search: SearchConfig
    distribution: DistributionConfig
    
    @classmethod
    def from_env(cls):
        """从环境变量创建配置"""
        load_dotenv()
        
        return cls(
            debug=os.getenv("DEBUG", "False").lower() == "true",
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            
            llm=LLMConfig(
                api_key=os.getenv("OPENAI_API_KEY", ""),
                api_base=os.getenv("LLM_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                model=os.getenv("LLM_MODEL", "deepseek-r1"),
                temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
                max_tokens=int(os.getenv("MAX_TOKENS", "4096")),
                use_tool_model=os.getenv("LLM_USE_TOOL_MODEL", "qwen2.5-72b-instruct"),
            ),
            
            search=SearchConfig(
                api_key=os.getenv("GOOGLE_API_KEY", ""),
                search_engine=os.getenv("SEARCH_ENGINE", "google"),
                max_results=int(os.getenv("SEARCH_MAX_RESULTS", "10")),
                timeout=int(os.getenv("SEARCH_TIMEOUT", "30")),
            ),
            
            distribution=DistributionConfig(
                wechat_official_account=WeChatOfficialAccountConfig(
                    enabled=os.getenv("WECHAT_OA_ENABLED", "False").lower() == "true",
                    api_url=os.getenv("WECHAT_API_URL", ""),
                    app_id=os.getenv("WECHAT_OA_APP_ID", ""),
                    app_secret=os.getenv("WECHAT_OA_APP_SECRET", ""),
                )
            )
        )
