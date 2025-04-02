"""
DeepresearchAgent - 专门用于搜索爬取相关数据进行深度研究的智能代理
"""

import os
import json
import logging
import asyncio
import requests
import re
import time
import random
from typing import Dict, List, Any, Optional, AsyncGenerator
from datetime import datetime
from pathlib import Path
import sys

# 将项目根目录添加到Python路径
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.append(str(ROOT_DIR))

from src.model.llm_client import llm_client
from src.tools.crawler.web_crawlers import CrawlerManager
from src.session.session_manager import session_manager
from src.session.message_manager import MessageManager
from src.memory.memory_manager import memory_manager
from src.database.vectordb.milvus_dao import milvus_dao
from src.token.token_counter import TokenCounter
from src.tools.crawler.crawler_config import crawler_config
from src.config.app_config import app_config
from src.tools.crawler.scheduled_crawler import ScheduledCrawler
from src.app.chat_bean import ChatMessage
from src.tools.crawler.web_crawlers import WebCrawler
from src.app.chat_bean import ChatResponse
from src.utils.json_parser import str2Json
from src.prompts.prompt_templates import PromptTemplates
from urllib.parse import quote
import uuid

logger = logging.getLogger(__name__)

class DeepresearchAgent:
    """
    专门用于搜索爬取相关数据进行深度研究的智能代理
    """
    
    def __init__(self, session_id: str = None):
        """
        初始化深度研究智能代理
        
        Args:
            session_id: 会话ID
        """
        session_id = session_id or str(uuid.uuid4())
        self.crawler_config = crawler_config
        self.session_id = session_id
        self.summary_limit = int(os.getenv("SUMMARY_LIMIT"))
        self.vectordb_limit = int(os.getenv("VECTORDB_LIMIT"))
        self.generate_query_num = int(os.getenv("GENERATE_QUERY_NUM"))
        self.milvus_dao = milvus_dao
        self.llm_client = llm_client
        self.crawler_manager = CrawlerManager()
        self.research_max_iterations = int(os.getenv("RESEARCH_MAX_ITERATIONS"))
        
        # 初始化数据库管理器
        try:
            self.session_manager = session_manager
            self.message_manager = MessageManager()
            self.memory_manager = memory_manager
            # 确保会话存在
            if not self.session_manager.get_session(self.session_id):
                self.session_manager.create_session(self.session_id)
            logger.info(f"数据库管理器初始化成功，会话ID: {self.session_id}")
        except Exception as e:
            logger.error(f"数据库管理器初始化失败: {str(e)}")
            self.session_manager = None
            self.message_manager = None
            self.memory_manager = None
        
        # 初始化Token计数器
        self.token_counter = TokenCounter(model_name=app_config.llm.model)
        
        # 记忆管理相关配置
        self.memory_threshold = int(os.getenv("MEMORY_THRESHOLD", "50"))  # 多少轮对话后生成长期记忆
        self.max_context_tokens = int(os.getenv("MAX_CONTEXT_TOKENS", "3072"))  # 上下文最大token数

    async def process_stream(self, message: ChatMessage) -> AsyncGenerator[dict, None]:
        """
        处理用户消息并以流式方式返回回复
        
        Args:
            message: 用户消息对象
            
        Returns:
            AsyncGenerator: 流式生成的回复
        """
        query = message.message
        
        # 保存用户消息到数据库
        if self.message_manager:
            self.message_manager.add_message(self.session_id, "user", query)
        
        # 保存到短期记忆
        if self.memory_manager:
            chat_history = self.memory_manager.get_chat_history(self.session_id) or []
            chat_history.append({"role": "user", "content": query})
            self.memory_manager.save_chat_history(self.session_id, chat_history)
        
        # 检测消息中是否包含URL
        urls = self._extract_urls(query)
        url_content_results = []
        
        # 如果发现URL，先处理URL内容
        if urls:
            yield {"type": "status", "content": f"发现{len(urls)}个URL，正在提取内容...", "phase": "url_extraction"}
            
            # 创建处理URL的任务列表，限制并发数量
            tasks = []
            semaphore = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_URLS", "3")))
            
            async def process_url_with_semaphore(url):
                async with semaphore:
                    return await self._process_url_content(url)
            
            # 创建所有URL处理任务
            for url in urls:
                tasks.append(asyncio.create_task(process_url_with_semaphore(url)))
            
            # 等待任务完成并处理结果
            for task in asyncio.as_completed(tasks):
                try:
                    result = await task
                    url_content_results.append(result)
                    
                    # 向用户返回URL处理结果
                    if result.get("is_quality_content", False):
                        # 包含摘要的高质量内容反馈
                        yield {
                            "type": "status", 
                            "content": f"已提取高质量内容: {result.get('url', '')}\n标题: {result.get('title', '未知')}\n\n{result.get('summary_result', '')}", 
                            "phase": "url_quality_check"
                        }
                    else:
                        # 低质量内容反馈
                        reason = result.get("reason", "内容质量不符合保存标准")
                        yield {
                            "type": "status", 
                            "content": f"提取的内容质量不佳: {result.get('url', '')}\n原因: {reason}", 
                            "phase": "url_quality_check"
                        }
                except Exception as e:
                    logger.error(f"处理URL内容时出错: {str(e)}", exc_info=True)
                    yield {"type": "status", "content": f"处理URL时出错: {str(e)}", "phase": "url_error"}
        
        # 判断是否要走URL处理流程（有URL且至少有一个高质量URL）
        has_quality_url = any(result.get("is_quality_content", False) for result in url_content_results)
        process_url_content = urls and has_quality_url
        
        # 处理URL内容路径
        if process_url_content:
            # 获取对话历史记录
            chat_history = await self._get_conversation_history()
            
            # 获取用户实际问题（可能需要从原查询中提取）
            clean_query = self._clean_query_from_urls(query)
            
            # 提取高质量URL内容用于回答
            quality_contents = []
            for result in url_content_results:
                if result.get("is_quality_content", False):
                    quality_contents.append({
                        "url": result.get("url"),
                        "title": result.get("title", "未知"),
                        "summary": result.get("summary_result", ""),
                        "content": result.get("content_summary", "")  # 使用摘要而非全文，避免token超限
                    })
            
            # 构建提示词用于回答问题
            prompt = f"用户问题: {clean_query}\n\n"
            prompt += "从URL提取的信息:\n"
            
            for idx, content in enumerate(quality_contents):
                prompt += f"[{idx+1}] {content['title']} ({content['url']})\n"
                prompt += f"{content['content']}\n\n"
            
            prompt += f"\n基于以上提取的信息，请回答用户问题: {clean_query}"
            
            # 添加历史上下文（如果有）
            if chat_history and len(chat_history) > 0:
                context_str = "\n\n对话历史上下文:\n"
                for msg in chat_history[-3:]:  # 仅使用最近3轮对话作为上下文
                    role = "用户" if msg.get("role") == "user" else "助手"
                    context_str += f"{role}: {msg.get('content', '')}\n"
                prompt += context_str
            
            yield {"type": "status", "content": "正在基于URL内容回答问题...", "phase": "url_analysis"}
            
            # 使用模型生成回复
            try:
                response_content = ""
                buffer = ""
                buffer_limit = 10
                async for chunk in self.llm_client.generate_with_streaming(
                    prompt, 
                    model=os.getenv("URL_ANALYSIS_MODEL", os.getenv("DEFAULT_MODEL"))
                ):
                    buffer += chunk
                    response_content += chunk
                    if len(buffer) >= buffer_limit or '\n' in buffer or '。' in buffer:
                        yield {"type": "content", "content": buffer}
                        buffer = ""
                
                if buffer:
                    yield {"type": "content", "content": buffer}
                
                # 保存助手响应到数据库
                if self.message_manager and response_content:
                    self.message_manager.add_message(self.session_id, "assistant", response_content)
                
                # 保存到短期记忆
                if self.memory_manager and response_content:
                    chat_history = self.memory_manager.get_chat_history(self.session_id) or []
                    chat_history.append({"role": "assistant", "content": response_content})
                    self.memory_manager.save_chat_history(self.session_id, chat_history)
                
                # 检查是否需要生成长期记忆
                if self.memory_manager:
                    chat_history = self.memory_manager.get_chat_history(self.session_id) or []
                    if len(chat_history) >= self.memory_threshold:
                        await self._generate_long_term_memory()
                
                yield {"type": "status", "content": "处理完成", "phase": "complete"}
                return
            except Exception as e:
                logger.error(f"生成回复时出错: {str(e)}", exc_info=True)
                yield {"type": "error", "content": f"生成回复时出错: {str(e)}"}
        
        # 标准研究流程 - 与原代码保持一致
        try:
            research_results = {"results": []}
            async for chunk in self._research(message):
                if isinstance(chunk, dict) and chunk.get("type") == "research_results":
                    research_results = chunk.get("result", {"results": []})
                else:
                    yield chunk
                
            response_content = ""
            async for chunk in self._deep_summary(message, research_results):
                if isinstance(chunk, dict):
                    yield chunk
                else:
                    response_content += chunk
                    yield {"type": "content", "content": chunk, "phase": "deep_summary"}
            
            # 保存助手响应到数据库
            if self.message_manager and response_content:
                self.message_manager.add_message(self.session_id, "assistant", response_content)
            
            # 保存到短期记忆
            if self.memory_manager and response_content:
                chat_history = self.memory_manager.get_chat_history(self.session_id) or []
                chat_history.append({"role": "assistant", "content": response_content})
                self.memory_manager.save_chat_history(self.session_id, chat_history)
            
            # 检查是否需要生成长期记忆
            if self.memory_manager:
                chat_history = self.memory_manager.get_chat_history(self.session_id) or []
                if len(chat_history) >= self.memory_threshold:
                    await self._generate_long_term_memory()
            
            yield {"type": "status", "content": "处理完成", "phase": "complete"}
        except Exception as e:
            logger.error(f"处理流时出错: {str(e)}", exc_info=True)
            yield {"type": "error", "content": f"处理您的查询时出错: {str(e)}"}

    async def _process_url_content(self, url: str) -> Dict:
        """
        处理URL内容：提取、评估质量、保存高质量内容
        
        Args:
            url: 目标URL
            
        Returns:
            Dict: 包含URL内容和处理结果的字典
        """
        logger.info(f"正在处理URL内容: {url}")
        result = {
            "url": url,
            "is_quality_content": False,
            "content": "",
            "title": "",
            "content_summary": "",
            "summary_result": "",
            "reason": "未获取到内容"
        }
        
        try:
            # 使用WebCrawler提取内容
            content = ""
            if self.crawler_manager.web_crawler.is_pdf_url(url):
                content = await self.crawler_manager.web_crawler.extract_pdf(url)
            else:
                content = await self.crawler_manager.web_crawler.fetch_url_md(url)
                
            if not content or len(content.strip()) == 0:
                logger.warning(f"URL内容为空: {url}")
                result["reason"] = "提取的内容为空"
                return result
                
            # 评估内容质量并获取摘要（已整合到一个API调用中）
            quality_result = await self.crawler_manager.web_crawler.assess_quality(url, content)
            
            # 更新结果
            result.update({
                "title": quality_result.get("title", ""),
                "content": content,
                "is_quality_content": quality_result.get("is_quality", False),
                "reason": quality_result.get("reason", "内容质量不符合保存标准"),
                "content_summary": quality_result.get("summary", ""),
                "summary_result": f"内容摘要:\n{quality_result.get('summary', '')}" if quality_result.get("summary") else "未能生成摘要"
            })
            
            # 如果是高质量内容，保存到知识库
            if result["is_quality_content"]:
                # 识别内容的主要意图（使用截断内容避免token超限）
                truncated_content = content[:3000] + ("..." if len(content) > 3000 else "")
                intent = await self._recognize_intent(truncated_content)
                logger.info(f"识别URL内容的领域意图: {intent}")
                
                # 准备保存数据
                article_data = [{
                    "url": url,
                    "content": content,
                    "title": result["title"],
                    "summary": result["content_summary"]
                }]
                
                # 异步保存，不阻塞主流程
                asyncio.create_task(self.crawler_manager.web_crawler.save_article(article_data, intent))
                logger.info(f"已将高质量内容异步保存到知识库: {url}, 意图: {intent}")
            else:
                logger.info(f"URL内容质量不佳，不保存: {url}")
                
            return result
            
        except Exception as e:
            logger.error(f"处理URL内容时出错: {url}, 错误: {str(e)}", exc_info=True)
            result["error"] = str(e)
            result["reason"] = f"处理出错: {str(e)}"
            return result
            
    def _clean_query_from_urls(self, query: str) -> str:
        """
        从查询中移除URL，获取用户的实际问题
        
        Args:
            query: 原始查询文本
            
        Returns:
            str: 清理URL后的查询文本
        """
        # URL正则表达式模式
        url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
        
        # 替换URL为占位符
        cleaned_query = re.sub(url_pattern, "[URL]", query)
        
        # 如果清理后只剩下[URL]，返回一个默认问题
        if cleaned_query.strip() == "[URL]" or cleaned_query.strip() == "":
            return "请分析这个URL的内容"
            
        return cleaned_query

    def _extract_urls(self, text: str) -> List[str]:
        """
        从文本中提取所有URL
        
        Args:
            text: 输入文本
            
        Returns:
            List[str]: 提取的URL列表
        """
        # URL正则表达式模式
        url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
        
        # 查找所有匹配项
        urls = re.findall(url_pattern, text)
        
        # 返回非空且有效的URL
        return [url for url in urls if url and self.crawler_manager.web_crawler.is_valid_url(url)]

    async def _deep_summary(self, message, research_results):
        """
        生成流式响应
        
        Args:
            message: 用户查询ChatMessage对象
            research_results: 研究结果
            
        Returns:
            流式响应生成器
        """
        query = message.message
        
        all_results = []
        for result in research_results.get("results", []):
            if 'content' in result and result['content']:
                all_results.append(result)
        
        if all_results:
            chat_history = await self._get_conversation_history()
            analysis_context = {
                "chat_history": chat_history,
                "query": query,
                "summaries": '\n'.join([result['content'] for result in all_results])
            }
            deep_analysis_prompt = PromptTemplates.format_deep_analysis_prompt(
                query, 
                '\n'.join([result['content'] for result in all_results]),
                context=json.dumps(analysis_context) if chat_history else ""
            )
            max_retries = 3
            retry_count = 0
            while retry_count < max_retries:
                try:
                    buffer = ""  # 用于缓冲少量token，以获得更流畅的体验
                    buffer_limit = 10  # 缓冲更多token后再发送，减少请求频率
                    async for chunk in self.llm_client.generate_with_streaming(deep_analysis_prompt):
                        buffer += chunk
                        if len(buffer) >= buffer_limit or '\n' in buffer or '。' in buffer:
                            yield {"type": "content", "content": buffer, "phase": "深度总结"}
                            buffer = ""
                    if buffer:
                        yield {"type": "content", "content": buffer, "phase": "深度总结"}
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.warning(f"流式连接出错，正在进行第{retry_count}次重试: {str(e)}")
                        yield {"type": "status", "content": f"连接出错，正在重试({retry_count}/{max_retries})...", "phase": "retry"}
                        await asyncio.sleep(1)  # 等待1秒后重试
                    else:
                        logger.error(f"流式连接最终失败: {str(e)}")
                        yield {"type": "error", "content": f"连接失败，请稍后重试: {str(e)}"}
                        raise
        else:
            yield {"type": "status", "content": "无法生成深度分析，未找到有效内容", "phase": "analysis_error"}
            yield {"type": "content", "content": "抱歉，我发现了一些相关信息，但无法生成有效的深度分析。请尝试使用更具体的查询。"}
        
        # 如果没有找到研究结果，仅使用历史对话回复
        yield {"type": "status", "content": "未找到相关信息，基于历史对话生成回复", "phase": "chat_response"}
        prompt = f"用户当前问题: {query}\n\n"
        if chat_history:
            prompt += "请基于以下历史对话回答用户的问题:\n\n"
            for msg in chat_history:
                role = "用户" if msg.get("role") == "user" else "助手"
                prompt += f"{role}: {msg.get('content', '')}\n\n"
        try:
            buffer = ""
            buffer_limit = 10
            async for chunk in self.llm_client.generate_with_streaming(prompt):
                buffer += chunk
                if len(buffer) >= buffer_limit or '\n' in buffer or '。' in buffer:
                    yield {"type": "content", "content": buffer}
                    buffer = ""
            if buffer:
                yield {"type": "content", "content": buffer}
        except Exception as e:
            logger.error(f"流式连接最终失败: {str(e)}")
            yield {"type": "error", "content": f"连接失败，请稍后重试: {str(e)}"}

    async def _get_conversation_history(self) -> List[Dict[str, str]]:
        """
        获取对话历史
        
        Returns:
            List[Dict[str, str]]: 对话历史列表
        """
        # 使用MemoryManager获取对话历史
        if self.memory_manager:
            chat_history = self.memory_manager.get_chat_history(self.session_id)
            if chat_history:
                # 使用token计数器限制历史大小
                return self.token_counter.fit_to_context_window(chat_history, self.max_context_tokens)
        
        return []

    async def _generate_long_term_memory(self):
        """
        生成长期记忆并保存到MySQL数据库
        
        此方法会从短期对话历史中提取重要信息，生成结构化的长期记忆
        同时提取用户特征并保存，用于后续个性化交互
        """
        if not self.memory_manager:
            logger.warning("记忆管理器未初始化，无法生成长期记忆")
            return
            
        try:
            # 获取短期记忆中的对话历史
            chat_history = self.memory_manager.get_chat_history(self.session_id)
            if not chat_history or len(chat_history) < self.memory_threshold:
                logger.info(f"对话历史不足以生成长期记忆: {len(chat_history) if chat_history else 0} < {self.memory_threshold}")
                return
            
            # 首先尝试提取用户特征，这样即使记忆生成失败也可以保存特征
            user_features = await self._extract_user_features(chat_history)
            if user_features:
                success = self.memory_manager.save_user_features(self.session_id, user_features)
                if success:
                    logger.info(f"为会话 {self.session_id} 提取并保存了用户特征")
                else:
                    logger.warning(f"为会话 {self.session_id} 保存用户特征失败")
            
            # 构建记忆生成提示，使用更结构化的模板
            memory_prompt = PromptTemplates.format_memory_generation_prompt(chat_history)
            
            # 生成记忆内容，指定使用COMPRESSION_MODEL环境变量指定的模型
            memory_content = await self.llm_client.generate(
                prompt=memory_prompt,
                system_message=PromptTemplates.get_memory_generation_system_message(),
                model=os.getenv("COMPRESSION_MODEL", self.llm_client.model)
            )
            
            # 验证记忆内容
            if not memory_content or len(memory_content.strip()) < 10:
                logger.warning(f"生成的记忆内容过短或为空: '{memory_content}'")
                return
                
            # 保存到长期记忆，确保同时保存到MySQL和Redis缓存
            success = self.memory_manager.save_memory(self.session_id, memory_content)
            if success:
                logger.info(f"为会话 {self.session_id} 生成并保存了长期记忆")
                
                # 清空MemoryManager中的短期记忆，重新开始累积
                self.memory_manager.save_chat_history(self.session_id, [])
            else:
                logger.warning(f"为会话 {self.session_id} 保存长期记忆失败")
                
        except Exception as e:
            logger.error(f"生成长期记忆时出错: {str(e)}", exc_info=True)

    async def _extract_user_features(self, chat_history):
        """
        从对话历史中提取用户特征
        
        Args:
            chat_history: 对话历史
        
        Returns:
            Dict[str, Any]: 用户特征
        """
        if not chat_history or len(chat_history) < 3:
            logger.info("对话历史过短，跳过用户特征提取")
            return {}
            
        try:
            # 构建特征提取提示
            feature_prompt = PromptTemplates.format_user_feature_extraction_prompt(chat_history)
            
            # 生成特征内容
            feature_content = await self.llm_client.generate(
                prompt=feature_prompt,
                system_message=PromptTemplates.get_user_feature_extraction_system_message(),
                model=os.getenv("COMPRESSION_MODEL", self.llm_client.model)
            )
            
            # 解析特征内容
            try:
                feature_data = str2Json(feature_content)
                features = feature_data.get("features", {})
                
                # 确保features格式正确
                if not isinstance(features, dict):
                    logger.warning(f"特征数据格式不正确，期望字典类型，实际为: {type(features)}")
                    return {}
                    
                # 简单校验特征数据结构
                if not any([
                    "interests" in features,
                    "knowledge_level" in features, 
                    "interaction_style" in features,
                    "goals" in features,
                    "language_preferences" in features
                ]):
                    logger.warning("特征数据缺少关键字段")
                
                return features
            except json.JSONDecodeError as je:
                logger.error(f"解析特征内容失败，响应不是有效的JSON: {je}", exc_info=True)
                # 尝试简单的恢复策略
                try:
                    # 尝试修复常见的JSON格式问题
                    fixed_content = feature_content.replace("'", '"').strip()
                    if not fixed_content.startswith('{'): 
                        fixed_content = '{' + fixed_content
                    if not fixed_content.endswith('}'): 
                        fixed_content = fixed_content + '}'
                    
                    feature_data = json.loads(fixed_content)
                    return feature_data.get("features", {})
                except Exception:
                    logger.error("JSON修复尝试失败", exc_info=True)
                    return {}
        except Exception as e:
            logger.error(f"提取用户特征时出错: {str(e)}", exc_info=True)
            return {}

    async def _research(self, message):
        """
        研究方法
        
        Args:
            message: 用户查询ChatMessage对象
            
        Returns:
            AsyncGenerator: 研究过程中的状态更新和最终结果
        """
        query = message.message
        
        intent = await self._recognize_intent(query)
        logger.info(f"识别{query}的查询意图是:{intent}")
        
        all_results = []
        iteration_count = 0

        try:
            max_token_limit = self.llm_client._get_model_token_limit(self.llm_client.model)
            # 为系统提示和回复预留空间
            available_token_limit = max_token_limit - 2048  # 预留2048个token给系统提示和回复
            logger.info(f"总结模型 {self.llm_client.model}的可用token限制: {available_token_limit}")
        except Exception as e:
            logger.warning(f"获取模型token限制失败: {e}，使用默认值12000")
            available_token_limit = 12000  # 默认预留12000个token
            
        # 跟踪当前已使用的token数量
        current_token_count = 0
        
        while iteration_count < self.research_max_iterations:
            try:
                evaluate_result = await self._evaluate_information(query, all_results)
                logger.info(f"{intent}场景解决{query}评估反思结果{evaluate_result}")
                if evaluate_result and evaluate_result["enough"]:
                    break
                yield {
                    "type": "research_process", 
                    "result": evaluate_result,
                    "phase": "evaluate"
                }
                search_url_list = evaluate_result["search_url"]
                if search_url_list:
                    for search_url in search_url_list:
                        urls = await self.crawler_manager.web_crawler.parse_sub_url(search_url)
                        if not urls:
                            continue
                        async for result in self.crawler_manager.web_crawler.fetch_article_stream(urls, intent):
                            if result['content'] and len(result['content'].strip()) > 0:
                                try:
                                    # 计算当前结果的token数量
                                    result_tokens = self.llm_client.count_tokens(
                                        f"URL: {result.get('url', '')}\n标题: {result.get('title', '')}\n内容: {result.get('content', '')}"
                                    )
                                    
                                    # 检查添加新结果是否会超过token限制
                                    if current_token_count + result_tokens > available_token_limit * 0.9:  # 预留10%的缓冲区
                                        logger.info(f"添加新结果将超过token限制，当前:{current_token_count}，新结果:{result_tokens}，限制:{available_token_limit}")
                                        
                                        # 通过LLM压缩内容以适应token限制
                                        await self._compress_results(query, all_results, result, available_token_limit)
                                        
                                        # 重新计算当前token数
                                        current_token_count = sum(self.llm_client.count_tokens(
                                            f"URL: {r.get('url', '')}\n标题: {r.get('title', '')}\n内容: {r.get('content', '')}"
                                        ) for r in all_results)
                                        
                                        logger.info(f"压缩后的token数: {current_token_count}")
                                    
                                    # 如果压缩后仍有空间，添加新结果
                                    if current_token_count + result_tokens <= available_token_limit:
                                        all_results.append(result)
                                        current_token_count += result_tokens
                                        
                                        yield {
                                            "type": "research_process", 
                                            "result": result,
                                            "phase": "web_search"
                                        }
                                except Exception as e:
                                    logger.error(f"处理搜索结果时出错: {str(e)}", exc_info=True)
            except Exception as e:
                logger.error(f"在{intent}场景解决{query}反思搜索迭代时出错: {str(e)}")
            
            if len(all_results) >= self.summary_limit:
                break
            iteration_count += 1
        
        # 确保结果不超过summary_limit
        if len(all_results) > self.summary_limit:
            all_results = all_results[:self.summary_limit]
        
        yield {"type": "research_results", "result": {"results": all_results}}

    async def _compress_results(self, query, all_results, new_result, token_limit):
        """
        使用LLM压缩已有结果，以便为新的高相关性内容腾出空间
        
        Args:
            query: 用户查询
            all_results: 当前已收集的所有结果
            new_result: 新的搜索结果
            token_limit: token限制
        """
        if not all_results:
            # 如果没有已有结果，则不需要压缩
            all_results.append(new_result)
            return
        
        # 准备所有内容(包括新内容)进行整体分析和压缩
        all_content = []
        for i, result in enumerate(all_results):
            content = f"""[文章{i}]
            URL: {result.get('url', '')}
            标题: {result.get('title', '')}
            内容: {result.get('content', '')}
            """
            all_content.append(content)
        
        # 新内容信息
        new_content = f"""[新文章]
        URL: {new_result.get('url', '')}
        标题: {new_result.get('title', '')}
        内容: {new_result.get('content', '')}
        """
        
        # 使用提示词模板
        unified_prompt = PromptTemplates.format_content_compression_prompt(
            query=query,
            existing_content=chr(10).join(all_content),
            new_content=new_content,
            token_limit=token_limit
        )
        
        try:
            logger.info(f"开始执行统一的内容压缩，当前有{len(all_results)}篇文章和1篇新文章")
            compression_response = await self.llm_client.generate(
                prompt=unified_prompt,
                system_message=PromptTemplates.get_content_compression_system_message(),
                model=os.getenv("COMPRESSION_MODEL", self.llm_client.model)
            )
            
            # 解析压缩结果
            try:
                result_data = json.loads(compression_response)
                compressed_results = result_data.get("compressed_results", [])
                decisions = result_data.get("decisions", {})
                
                # 日志记录决策信息
                logger.info(f"压缩决策: {decisions.get('reasoning', '无详细决策')}")
                logger.info(f"保留了{len(compressed_results)}篇文章")
                
                # 清空当前结果并用压缩后的结果替换
                all_results.clear()
                
                # 处理每篇压缩后的文章
                for article in compressed_results:
                    original_index = article.get("original_index")
                    
                    # 跳过格式不正确的项
                    if not isinstance(original_index, (int, float)) or not article.get("content"):
                        continue
                        
                    if original_index == -1:
                        # 这是新文章
                        processed_article = new_result.copy()
                        processed_article["content"] = article.get("content")
                        processed_article["compressed"] = article.get("compressed", True)
                    else:
                        # 这是已有文章
                        if 0 <= original_index < len(all_content):
                            # 从原内容获取文章对象，并更新为压缩后的内容
                            processed_article = all_results[original_index].copy() if original_index < len(all_results) else {}
                            processed_article["content"] = article.get("content")
                            processed_article["compressed"] = article.get("compressed", True)
                            processed_article["url"] = article.get("url", processed_article.get("url", ""))
                            processed_article["title"] = article.get("title", processed_article.get("title", ""))
                    
                    # 添加处理后的文章到结果集
                    if "content" in processed_article and processed_article["content"]:
                        all_results.append(processed_article)
                
                # 确保结果不为空
                if not all_results:
                    logger.warning("压缩后结果为空，添加原始新文章")
                    all_results.append(new_result)
                    
            except json.JSONDecodeError as je:
                logger.error(f"解析压缩结果失败，响应不是有效的JSON: {je}")
                self._apply_fallback_strategy(all_results, new_result)
                
        except Exception as e:
            logger.error(f"执行统一内容压缩时出错: {str(e)}", exc_info=True)
            self._apply_fallback_strategy(all_results, new_result)

    def _apply_fallback_strategy(self, all_results, new_result):
        """简单的备用压缩策略，当高级压缩失败时使用"""
        try:
            # 如果有超过3篇文章，保留后半部分(较新的内容)
            if len(all_results) > 3:
                keep_count = max(2, len(all_results) // 2)
                logger.info(f"应用备用压缩策略: 保留最新的{keep_count}篇文章")
                all_results[:] = all_results[-keep_count:]
            
            # 添加新结果
            all_results.append(new_result)
        except Exception as e:
            logger.error(f"应用备用压缩策略时出错: {str(e)}")
            # 确保至少有新结果
            if len(all_results) > 0:
                all_results.pop(0)  # 移除最旧的一篇
            all_results.append(new_result)

    async def _evaluate_information(self, query, results):
        """
        使用LLM评估已获取的信息是否足够回答用户查询
        
        Args:
            query: 用户查询
            results: 已获取的结果
            
        Returns:
            bool: 信息是否足够
        """
        context_text = ""
        if results:
            for i, result in enumerate(results):
                if 'content' in result and result['content']:
                    snippet = result['content']
                    context_text += f"文档{i}: {snippet}...\n"
        
        prompt = PromptTemplates.format_evaluate_information_prompt(query, context_text)
        
        try:
            response = await self.llm_client.generate(
                prompt=prompt, 
                system_message=PromptTemplates.get_system_message(),
                model=os.getenv("EVALUATE_INFORMATION_MODEL")
            )
            return str2Json(response)
        except Exception as e:
            logger.error(f"评估信息充分性时出错: {str(e)}", exc_info=True)
            return {}

    async def _recognize_intent(self, query: str) -> str:
        """
        识别用户查询的意图，确定对应的研究场景
        
        Args:
            query: 用户查询文本
            
        Returns:
            str: 识别的场景名称
        """
        try:
            prompt = PromptTemplates.format_intent_recognition_prompt(query)
            response = await self.llm_client.generate(
                prompt=prompt,
                system_message=PromptTemplates.get_system_message(),
                model=os.getenv("INTENT_RECOGNITION_MODEL")
            )
            return response.strip().lower()
        except Exception as e:
            logger.error(f"意图识别出错: {str(e)}")
            return self.crawler_config.get_default_scenario()