import os
from typing import Optional
from pydantic import BaseModel
from dotenv import load_dotenv


class LLMConfig(BaseModel):
    """LLM模型配置"""
    api_key: str
    api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "deepseek-r1"
    temperature: float = 0.7
    max_tokens: int = 4096
    use_tool_model: str = "qwen2.5-72b-instruct"


class AppConfig(BaseModel):
    """应用全局配置"""
    debug: bool = False
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    llm: LLMConfig
    
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
                max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
                use_tool_model=os.getenv("LLM_USE_TOOL_MODEL", "qwen2.5-72b-instruct"),
            )
        )


app_config = AppConfig.from_env()