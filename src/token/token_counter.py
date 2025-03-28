"""
Token计数器模块，用于计算文本的token数量并实现滑动窗口控制
"""

import logging
import tiktoken
from typing import List, Dict, Any, Optional, Union

logger = logging.getLogger(__name__)

class TokenCounter:
    """处理对话上下文的token计数和滑动窗口控制"""
    
    def __init__(self, model_name: str = "gpt-3.5-turbo"):
        """
        初始化Token计数器
        
        Args:
            model_name: 模型名称，用于选择合适的编码器
        """
        self.model_name = model_name
        self.encoder = self._get_encoder(model_name)
        
        # 不同模型的上下文窗口大小
        self.context_window_sizes = {
            "gpt-3.5-turbo": 4096,
            "gpt-3.5-turbo-16k": 16384,
            "gpt-4": 8192,
            "gpt-4-32k": 32768
        }
        # 默认预留给响应的token数
        self.response_token_reserve = 1024
    
    def _get_encoder(self, model_name: str):
        """
        根据模型名称获取合适的编码器
        
        Args:
            model_name: 模型名称
            
        Returns:
            tiktoken编码器
        """
        try:
            # 根据模型选择编码器
            if "gpt-4" in model_name:
                return tiktoken.encoding_for_model("gpt-4")
            elif "gpt-3.5-turbo" in model_name:
                return tiktoken.encoding_for_model("gpt-3.5-turbo")
            else:
                # 默认使用cl100k_base编码器
                return tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.error(f"获取编码器失败: {str(e)}")
            # 如果失败，尝试使用最通用的编码器
            return tiktoken.get_encoding("cl100k_base")
    
    def count_tokens(self, text: str) -> int:
        """
        计算文本的token数量
        
        Args:
            text: 需要计算的文本
            
        Returns:
            int: token数量
        """
        try:
            return len(self.encoder.encode(text))
        except Exception as e:
            logger.error(f"计算token失败: {str(e)}")
            # 如果编码失败，使用简单的估算（每4个字符约1个token）
            return len(text) // 4
    
    def count_message_tokens(self, message: Dict[str, str]) -> int:
        """
        计算一条消息的token数量
        
        Args:
            message: 消息字典，包含role和content
            
        Returns:
            int: token数量
        """
        # 消息格式token开销（每条消息的元数据）
        token_overhead = 4  # 基础开销
        
        # 计算角色和内容的token
        role_tokens = self.count_tokens(message.get("role", ""))
        content_tokens = self.count_tokens(message.get("content", ""))
        
        return token_overhead + role_tokens + content_tokens
    
    def count_conversation_tokens(self, messages: List[Dict[str, str]]) -> int:
        """
        计算整个对话的token数量
        
        Args:
            messages: 消息列表
            
        Returns:
            int: 总token数量
        """
        total_tokens = 0
        for message in messages:
            total_tokens += self.count_message_tokens(message)
        
        # 添加对话开始的基础token开销
        return total_tokens + 2  # 对话开始的固定开销
    
    def get_max_context_size(self) -> int:
        """
        获取当前模型的最大上下文窗口大小
        
        Returns:
            int: 最大上下文窗口大小
        """
        return self.context_window_sizes.get(self.model_name, 4096)
    
    def fit_to_context_window(self, messages: List[Dict[str, str]], max_tokens: Optional[int] = None) -> List[Dict[str, str]]:
        """
        将消息列表裁剪到适合上下文窗口的大小
        
        Args:
            messages: 原始消息列表
            max_tokens: 自定义最大token数，默认为当前模型的上下文窗口大小减去响应预留
            
        Returns:
            List[Dict[str, str]]: 裁剪后的消息列表
        """
        if not messages:
            return []
        
        if max_tokens is None:
            max_tokens = self.get_max_context_size() - self.response_token_reserve
        
        # 复制消息列表以避免修改原始数据
        messages_copy = messages.copy()
        
        # 系统消息需要优先保留
        system_messages = [m for m in messages_copy if m.get("role") == "system"]
        system_tokens = sum(self.count_message_tokens(m) for m in system_messages)
        
        # 非系统消息
        non_system_messages = [m for m in messages_copy if m.get("role") != "system"]
        
        # 必须保留的最新消息（至少保留最后一条用户消息）
        must_keep_messages = []
        total_must_keep_tokens = 0
        
        # 如果有用户消息，保留最后一条
        user_messages = [m for m in non_system_messages if m.get("role") == "user"]
        if user_messages:
            last_user_message = user_messages[-1]
            must_keep_messages.append(last_user_message)
            total_must_keep_tokens += self.count_message_tokens(last_user_message)
            non_system_messages.remove(last_user_message)
        
        # 计算可用的token数
        available_tokens = max_tokens - system_tokens - total_must_keep_tokens
        
        # 从最新到最旧排序剩余消息
        remaining_messages = sorted(non_system_messages, key=lambda m: messages_copy.index(m), reverse=True)
        
        # 选择尽可能多的消息，直到达到可用token限制
        selected_messages = []
        for message in remaining_messages:
            message_tokens = self.count_message_tokens(message)
            if available_tokens >= message_tokens:
                selected_messages.append(message)
                available_tokens -= message_tokens
            else:
                break
        
        # 重新按原始顺序排列所有保留的消息
        final_messages = system_messages + sorted(selected_messages + must_keep_messages, 
                                                 key=lambda m: messages_copy.index(m))
        
        logger.info(f"对话被裁剪：从{len(messages)}条消息减少到{len(final_messages)}条，总token数约为{self.get_max_context_size() - available_tokens}")
        
        return final_messages
    
    def track_token_usage(self, prompt_tokens: int, completion_tokens: int) -> Dict[str, int]:
        """
        记录token使用情况
        
        Args:
            prompt_tokens: 提示词token数
            completion_tokens: 完成词token数
            
        Returns:
            Dict[str, int]: token使用统计
        """
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens
        }
