import os
import logging
import json
from typing import Dict, Any, Optional, List, AsyncGenerator
import time
import asyncio
import openai
from src.prompts.prompt_templates import PromptTemplates
from src.config.app_config import app_config

logger = logging.getLogger(__name__)

class LLMClient:
    """
    LLM客户端，封装对LLM API的调用
    """
    
    def __init__(self, api_key: str, api_base: str = None,
                model: str = None, temperature: float = 0.7,
                max_tokens: int = 4096, use_tool_model: str = None):
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_tool_model = use_tool_model
        self._init_client()
    
    def _init_client(self):
        """初始化API客户端"""
        # 配置OpenAI
        try:
            openai.api_key = self.api_key
            
            # 如果是DashScope API，确保URL路径正确
            if "dashscope" in self.api_base:
                # 确保API基础URL不包含chat/completions路径，这将在API调用时自动添加
                if self.api_base.endswith('/'):
                    self.api_base = self.api_base[:-1]
                    
                # 从URL中移除可能的重复路径
                if "/chat/completions" in self.api_base:
                    self.api_base = self.api_base.replace("/chat/completions", "")
                
                # 确保v1后面有斜杠，避免形成v1chat这样的错误路径
                if self.api_base.endswith('v1'):
                    self.api_base = f"{self.api_base}/"
                
                logger.info(f"检测到DashScope API，使用基础URL: {self.api_base}")
            
            # 设置OpenAI基础URL
            openai.base_url = self.api_base
            
            # 测试连接
            logger.info(f"初始化LLM客户端，模型: {self.model}")
        except Exception as e:
            logger.error(f"初始化OpenAI客户端时出错: {e}", exc_info=True)
    
    async def generate(self, prompt: str, max_tokens: Optional[int] = None, 
                     temperature: Optional[float] = None, 
                     tools: Optional[List[Dict[str, Any]]] = None,
                     system_message: Optional[str] = None) -> str:
        """
        生成文本
        
        Args:
            prompt: 提示词
            max_tokens: 最大生成长度，None表示使用默认值
            temperature: 温度参数，None表示使用默认值
            tools: 可用工具列表
            system_message: 系统消息
            
        Returns:
            str: 生成的文本
        """
        # 准备消息
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        else:
            # 使用默认系统消息
            messages.append({"role": "system", "content": PromptTemplates.get_system_message()})
        
        # 添加用户消息
        messages.append({"role": "user", "content": prompt})
        
        # 重试机制
        max_retries = 2
        retry_delay = 2  # 初始等待时间（秒）
        
        for attempt in range(max_retries):
            try:
                # 参数设置
                params = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature if temperature is not None else self.temperature,
                    "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
                }
                
                # 如果有工具配置，添加到参数中，并且设置支持工具调用的模型
                if tools:
                    params["model"] = self.use_tool_model
                    params["tools"] = tools
                
                # 检查是否是DashScope API，并添加流式参数
                if "dashscope" in self.api_base:
                    logger.info(f"使用DashScope API，启用流式模式")
                    params["stream"] = True
                    
                    # 调用API并处理流式响应
                    full_response = ""
                    logger.info(f"使用API基础URL: {openai.base_url}")
                    stream_resp = openai.chat.completions.create(**params)
                    
                    # 从流式响应中收集完整响应
                    for chunk in stream_resp:
                        if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content is not None:
                            content = chunk.choices[0].delta.content
                            full_response += content
                    
                    return full_response
                else:
                    # 标准OpenAI调用
                    logger.info(f"使用API基础URL: {openai.base_url}")
                    response = openai.chat.completions.create(**params)
                    return response.choices[0].message.content
            
            except Exception as e:
                logger.error(f"调用LLM API时出错 (尝试 {attempt+1}/{max_retries}): {e}", exc_info=True)
                
                if attempt < max_retries - 1:
                    # 指数退避策略
                    sleep_time = retry_delay * (2 ** attempt)
                    logger.info(f"等待 {sleep_time} 秒后重试...")
                    time.sleep(sleep_time)
                else:
                    logger.error("达到最大重试次数，无法获取LLM响应")
                    raise
    
    async def generate_with_streaming(self, prompt: str,
                                    max_tokens: Optional[int] = None,
                                    temperature: Optional[float] = None,
                                    system_message: Optional[str] = None) -> AsyncGenerator[str, None]:
        """
        流式生成文本
        
        Args:
            prompt: 提示词
            max_tokens: 最大生成长度
            temperature: 温度
            system_message: 系统消息
            
        Returns:
            AsyncGenerator[str, None]: 生成的文本流
        """
        # 使用默认系统消息
        if not system_message:
            system_message = PromptTemplates.get_system_message()
        
        # 准备消息
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ]
        
        # 参数设置
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "stream": True
        }
        
        try:
            # 调用API并处理流式响应
            stream_resp = openai.chat.completions.create(**params)
            
            for chunk in stream_resp:
                if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    yield content
        except Exception as e:
            logger.error(f"流式生成文本时出错: {e}", exc_info=True)
            
            # 出错时尝试使用非流式方式生成
            try:
                logger.info("尝试使用非流式方式生成...")
                non_streaming_response = await self.generate(prompt, max_tokens, temperature, None, system_message)
                yield non_streaming_response
            except Exception as e2:
                logger.error(f"非流式生成文本时出错: {e2}", exc_info=True)
                yield f"生成文本时出错: {str(e2)}"  

llm_client = LLMClient(api_key=app_config.llm.api_key, 
                       model=app_config.llm.model, 
                       api_base=app_config.llm.api_base)