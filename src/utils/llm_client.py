import os
import logging
import json
from typing import Dict, Any, Optional, List, AsyncGenerator
import time
import asyncio
import openai

logger = logging.getLogger(__name__)

class LLMClient:
    """
    LLM客户端，封装对LLM API的调用
    """
    
    def __init__(self, api_key: str, api_base: str = "https://api.openai.com/v1",
                model: str = "gpt-4-turbo-preview", temperature: float = 0.7,
                max_tokens: int = 4096, use_tool_model: str = "gpt-4-turbo-preview"):
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_tool_model = use_tool_model
        
        # 初始化API客户端
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
    
    async def generate_with_json(self, prompt: str, json_schema: Dict[str, Any],
                               max_tokens: Optional[int] = None,
                               temperature: Optional[float] = None,
                               system_message: Optional[str] = None) -> Dict[str, Any]:
        """
        生成符合JSON模式的结构化输出
        
        Args:
            prompt: 提示词
            json_schema: JSON模式定义
            max_tokens: 最大生成长度
            temperature: 温度
            system_message: 系统消息
            
        Returns:
            Dict[str, Any]: 解析后的JSON对象
        """
        # 构建工具定义
        json_tool = {
            "type": "function",
            "function": {
                "name": "json_output",
                "description": "Output in JSON format",
                "parameters": json_schema
            }
        }
        
        # 在系统消息中添加JSON输出指令
        json_system_message = system_message or ""
        json_system_message += "\nYou must respond with a valid JSON object that conforms to the provided schema."
        
        try:
            # 调用LLM生成
            tools = [json_tool]
            
            # 使用流式模式生成
            if "dashscope" in self.api_base:
                logger.info(f"使用DashScope API进行JSON生成，启用流式模式")
                
                # 准备消息
                messages = []
                if json_system_message:
                    messages.append({"role": "system", "content": json_system_message})
                
                # 添加用户消息
                messages.append({"role": "user", "content": prompt})
                
                # 参数设置
                params = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature if temperature is not None else self.temperature,
                    "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
                    "stream": True
                }

                # 如果有工具配置，添加到参数中，并且设置支持工具调用的模型
                if tools:
                    params["model"] = self.use_tool_model
                    params["tools"] = tools
                
                # 调用API并处理流式响应
                json_str = ""
                stream_resp = openai.chat.completions.create(**params)
                
                for chunk in stream_resp:
                    if hasattr(chunk.choices[0].delta, 'tool_calls') and chunk.choices[0].delta.tool_calls:
                        tool_call = chunk.choices[0].delta.tool_calls[0]
                        if hasattr(tool_call, 'function') and tool_call.function and hasattr(tool_call.function, 'arguments'):
                            json_str += tool_call.function.arguments or ""
                
                # 解析JSON
                try:
                    result = json.loads(json_str)
                    return result
                except json.JSONDecodeError as e:
                    logger.error(f"解析JSON响应时出错: {e}\nJSON字符串: {json_str}", exc_info=True)
                    raise
            else:
                # 标准OpenAI调用
                response = await self.generate(prompt, max_tokens, temperature, system_message, tools)
                
                # 如果是工具调用的响应
                if hasattr(response, 'choices') and response.choices[0].message.tool_calls:
                    json_str = response.choices[0].message.tool_calls[0].function.arguments
                    return json.loads(json_str)
                else:
                    # 尝试直接解析响应
                    try:
                        return json.loads(response)
                    except:
                        return {"error": "无法解析JSON输出", "raw_response": response}
        
        except Exception as e:
            logger.error(f"生成JSON输出时出错: {e}", exc_info=True)
            return {"error": str(e)}

    async def generate_with_streaming(self, prompt: str, 
                                    max_tokens: Optional[int] = None,
                                    temperature: Optional[float] = None,
                                    system_message: Optional[str] = None) -> AsyncGenerator[str, None]:
        """
        流式生成文本
        
        Args:
            prompt: 提示词
            max_tokens: 最大生成长度，None表示使用默认值
            temperature: 温度参数，None表示使用默认值
            system_message: 系统消息
            
        Returns:
            AsyncGenerator[str, None]: 文本流
        """                
        # 设置参数默认值
        max_tokens = max_tokens or self.max_tokens
        temperature = temperature or self.temperature
        system_message = system_message or "You are a helpful assistant."
        
        # 最大重试次数
        max_retries = 3
        retry_count = 0
        retry_delay = 1  # 初始延迟1秒
        
        while retry_count < max_retries:
            try:
                logger.info(f"开始流式生成文本 (尝试 {retry_count + 1}/{max_retries})")
                
                # 真实的OpenAI API调用
                messages = [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ]
                
                # 创建流式响应 - 不需要 await
                response = openai.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True
                )
                
                # 流式处理响应
                collected_chunks = []
                collected_messages = ""
                
                # 处理每个流式事件
                try:
                    for chunk in response:
                        collected_chunks.append(chunk)  # 保存响应块以便调试
                        
                        # 防御性编程: 检查所有可能的属性
                        chunk_message = None
                        if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                            if hasattr(chunk.choices[0], 'delta'):
                                if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content is not None:
                                    chunk_message = chunk.choices[0].delta.content
                        
                        if chunk_message is not None:
                            collected_messages += chunk_message
                            logger.debug(f"收到第 {len(collected_chunks)} 个响应块: '{chunk_message}' 累计长度: {len(collected_messages)}")
                            yield chunk_message
                        else:
                            logger.debug(f"收到第 {len(collected_chunks)} 个空内容响应块")
                    
                    # 如果能走到这里，说明成功完成了流式生成
                    logger.info(f"流式响应完成，总共收到 {len(collected_chunks)} 个块，总响应长度: {len(collected_messages)}")
                    return  # 成功完成，退出函数
                    
                except openai.APIError as api_error:
                    # 特别处理API错误
                    if "500" in str(api_error) and "InternalError" in str(api_error):
                        logger.error(f"遇到OpenAI服务器内部错误 (尝试 {retry_count + 1}/{max_retries}): {str(api_error)}")
                        # 准备重试
                        retry_count += 1
                        if retry_count < max_retries:
                            logger.info(f"等待 {retry_delay} 秒后重试...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2  # 指数退避
                            continue
                        else:
                            # 使用备选方法
                            logger.warning("达到最大重试次数，尝试使用非流式生成")
                            try:
                                # 尝试非流式生成文本
                                non_streaming_response = await self.generate(prompt, max_tokens, temperature, system_message)
                                yield "由于流式生成出错，切换为一次性响应：\n\n"
                                yield non_streaming_response
                                return
                            except Exception as backup_error:
                                logger.error(f"备选方法也失败: {str(backup_error)}")
                                yield f"无法生成响应。服务器可能暂时不可用，请稍后再试。错误详情: {str(api_error)}"
                                return
                    else:
                        # 其他API错误
                        raise
                        
            except Exception as e:
                error_message = f"流式生成文本时出错: {str(e)}"
                logger.error(error_message, exc_info=True)
                
                # 增加重试逻辑
                retry_count += 1
                if retry_count < max_retries:
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                else:
                    # 所有重试都失败
                    logger.error(f"达到最大重试次数 ({max_retries})，无法完成请求")
                    # 在流式生成中返回错误信息
                    yield f"生成回复时出错，已尝试 {max_retries} 次: {str(e)}"
                    
                    # 尝试使用备选方法
                    logger.warning("尝试使用非流式生成作为备选方案")
                    try:
                        # 尝试非流式生成文本
                        non_streaming_response = await self.generate(prompt, max_tokens, temperature, system_message)
                        yield "\n\n切换为非流式生成，响应如下：\n\n"
                        yield non_streaming_response
                    except Exception as backup_error:
                        logger.error(f"备选方法也失败: {str(backup_error)}")
                        yield "\n\n无法完成响应生成。请稍后再试。"
                    return
