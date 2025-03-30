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
from src.tools.crawler.config import crawler_config
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

    async def process_stream(self, message, **kwargs):
        """
        流式处理用户查询，逐步返回处理结果
        
        Args:
            message: 用户查询ChatMessage对象
            **kwargs: 其他参数
            
        Returns:
            AsyncGenerator[Dict[str, Any], None]: 处理结果流
        """
        # 保存用户消息到数据库
        if self.message_manager:
            self.message_manager.add_message(self.session_id, "user", message.message)
        
        # 保存到短期记忆
        if self.memory_manager:
            chat_history = self.memory_manager.get_chat_history(self.session_id) or []
            chat_history.append({"role": "user", "content": message.message})
            self.memory_manager.save_chat_history(self.session_id, chat_history)
        
        try:
            # 使用带进度更新的研究方法
            research_results = {"results": []}
            async for chunk in self._research_with_progress(message):
                if isinstance(chunk, dict) and chunk.get("type") == "research_results":
                    research_results = chunk.get("data", {"results": []})
                else:
                    yield chunk
            
            # 生成流式响应
            response_content = ""
            async for chunk in self._generate_response_stream(message, research_results):
                if isinstance(chunk, dict):
                    yield chunk
                else:
                    response_content += chunk
                    yield {"type": "content", "content": chunk}
            
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
            
            # 处理完成
            yield {"type": "status", "content": "处理完成", "phase": "complete"}
        except Exception as e:
            logger.error(f"处理流时出错: {str(e)}", exc_info=True)
            yield {"type": "error", "content": f"处理您的查询时出错: {str(e)}"}

    async def _generate_response_stream(self, message, research_results):
        """
        生成流式响应
        
        Args:
            message: 用户查询ChatMessage对象
            research_results: 研究结果
            
        Returns:
            流式响应生成器
        """
        query = message.message
        
        try:
            results = research_results.get("results", [])
            
            # 获取历史对话
            chat_history = await self._get_conversation_history()
            
            if results:
                all_summaries = []
                for result in results:
                    if 'content' in result and result['content']:
                        all_summaries.append(result['content'])
                
                if all_summaries:
                    yield {"type": "status", "content": "正在生成思考与分析...", "phase": "analysis_deep"}
                    
                    analysis_context = {
                        "chat_history": chat_history,
                        "query": query,
                        "summaries": '\n'.join(all_summaries)
                    }
                    deep_analysis_prompt = PromptTemplates.format_deep_analysis_prompt(
                        query, 
                        '\n'.join(all_summaries),
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
                                    yield {"type": "content", "content": buffer}
                                    buffer = ""
                            if buffer:
                                yield {"type": "content", "content": buffer}
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
            else:
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
        except Exception as e:
            logger.error(f"生成响应时出错: {str(e)}", exc_info=True)
            yield {"type": "error", "content": f"生成响应时出错: {str(e)}"}

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
        """生成长期记忆并保存到MySQL"""
        try:
            # 获取短期记忆中的对话历史
            chat_history = self.memory_manager.get_chat_history(self.session_id)
            if not chat_history or len(chat_history) < self.memory_threshold:
                return
            
            # 构建记忆生成提示
            memory_prompt = "请总结以下对话的关键信息，提取重要的事实、观点和结论:\n\n"
            for msg in chat_history:
                role = "用户" if msg.get("role") == "user" else "助手"
                memory_prompt += f"{role}: {msg.get('content', '')}\n\n"
            
            # 生成记忆内容
            memory_content = await self.llm_client.generate(memory_prompt)
            
            # 保存到长期记忆
            if memory_content and self.memory_manager:
                self.memory_manager.save_memory(self.session_id, memory_content)
                logger.info(f"为会话 {self.session_id} 生成了长期记忆")
                
                # 清空MemoryManager中的短期记忆，重新开始累积
                self.memory_manager.save_chat_history(self.session_id, [])
        except Exception as e:
            logger.error(f"生成长期记忆时出错: {str(e)}")

    async def _research_with_progress(self, message):
        """
        带有进度更新的研究方法，在研究的每个阶段发送进度更新
        
        Args:
            message: 用户查询ChatMessage对象
            
        Returns:
            AsyncGenerator: 研究过程中的状态更新和最终结果
        """
        query = message.message
        
        # 识别意图
        intent = await self._recognize_intent(query)
        
        # 生成搜索查询
        search_queries = await self._generate_search_queries(message)
        yield {"type": "status", "phase": "queries", "query_list": search_queries}
        
        all_results = []
        iteration_count = 0
        while iteration_count < self.research_max_iterations:
            for query in search_queries:
                try:
                    url_formats = self.crawler_config.get_search_url_formats(intent)
                    all_urls = set()
                    for platform, url_format in url_formats.items():
                        if 'arxiv' in platform:
                            sub_urls = await self.crawler_manager.arxiv_crawler.parse_sub_url(query)
                            sub_urls = [url for url in sub_urls if url not in all_urls]
                            if not sub_urls:
                                continue
                            yield {
                                "type": "status", 
                                "query": query,
                                "platform": platform,
                                "phase": "research"
                            }
                            all_urls.update(sub_urls)
                            async for result in self.crawler_manager.arxiv_crawler.fetch_article_stream(sub_urls):
                                all_results.append(result)
                                yield {
                                    "type": "status", 
                                    "result": result,
                                    "phase": "research_detail"
                                }
                        elif 'github' in platform:
                            sub_urls = await self.crawler_manager.github_crawler.parse_sub_url(query)
                            sub_urls = [url for url in sub_urls if url not in all_urls]
                            if not sub_urls:
                                continue
                            yield {
                                "type": "status", 
                                "query": query,
                                "platform": platform,
                                "phase": "research"
                            }
                            all_urls.update(sub_urls)
                            async for result in self.crawler_manager.github_crawler.fetch_article_stream(sub_urls):
                                all_results.append(result)
                                yield {
                                    "type": "status", 
                                    "result": result,
                                    "phase": "research_detail"
                                }
                        else:
                            search_url = url_format.format(quote(query))
                            sub_urls = await self.crawler_manager.web_crawler.parse_sub_url(search_url)
                            sub_urls = [url for url in sub_urls if url not in all_urls]
                            if not sub_urls:
                                continue
                            yield {
                                "type": "status", 
                                "query": query,
                                "platform": platform,
                                "phase": "research"
                            }
                            all_urls.update(sub_urls)
                            async for result in self.crawler_manager.web_crawler.fetch_article_stream(sub_urls):
                                all_results.append(result)
                                yield {
                                    "type": "status", 
                                    "result": result,
                                    "phase": "research_detail"
                                }
                except Exception as e:
                    logger.error(f"在{intent}场景搜索{query}时出错: {str(e)}", exc_info=True)

            yield {"type": "status", "phase": "vector_search", "scenario": intent}
            all_contents = milvus_dao.search(
                collection_name=self.crawler_config.get_collection_name(intent),
                data=milvus_dao.generate_embeddings(search_queries),
                limit=self.summary_limit,
                output_fields=["url", "content"],
            )
            unique_contents = {}
            for query_contents in all_contents:
                if not query_contents:
                    continue
                for contents in query_contents:
                    entity = contents['entity']
                    if isinstance(entity, dict) and 'content' in entity and entity['content'] and len(entity['content'].strip()) > 0 and 'url' in entity and entity['url'] not in unique_contents:
                        unique_contents[entity['url']] = entity
            result = list(unique_contents.values())
            if result:
                yield {"type": "status", "phase": "vector_search_detail", "result": result}
                all_results.extend(result)

            if len(all_results) >= self.summary_limit:
                break
            if await self._evaluate_information_sufficiency(query, all_results):
                break
            if iteration_count < self.research_max_iterations - 1:
                additional_queries = await self._generate_additional_queries(query, all_results)
                search_queries = additional_queries
                yield {"type": "status", "phase": "queries", "query_list": search_queries}
            iteration_count += 1

        asyncio.create_task(self._async_save_to_vectordb(query, intent, all_results.copy()))
        
        if len(all_results) > self.summary_limit:
            all_results = all_results[:self.summary_limit]
        
        yield {"type": "research_results", "data": {"results": all_results}}

    async def _async_save_to_vectordb(self, query, scenario, results):
        """
        异步将研究结果保存到向量数据库，不阻塞主流程
        
        Args:
            query: 用户查询
            results: 研究结果
        """
        if not results:
            return
        if len(results) > self.vectordb_limit:
            results = results[:self.vectordb_limit]
        try:
            self.crawler_manager.web_crawler.save_article(results, scenario)
            logger.info(f"成功异步保存研究结果到向量数据库: query={query}, scenario={scenario}")
        except Exception as e:
            logger.error(f"异步保存到向量数据库时出错: {str(e)}", exc_info=True)
            # 异步执行不能使用yield，只记录日志不影响主流程

    async def _evaluate_information_sufficiency(self, query, results):
        """
        使用LLM评估已获取的信息是否足够回答用户查询
        
        Args:
            query: 用户查询
            results: 已获取的结果
            
        Returns:
            bool: 信息是否足够
        """
        if not results:
            return False
            
        context_text = ""
        for i, result in enumerate(results):
            if 'content' in result and result['content']:
                snippet = result['content']
                context_text += f"文档{i}: {snippet}...\n"
        
        prompt = PromptTemplates.format_information_sufficiency_prompt(query, context_text)
        
        try:
            response = await self.llm_client.generate(prompt)
            if "SUFFICIENT" in response.strip().upper():
                return True
            return False
        except Exception as e:
            logger.error(f"评估信息充分性时出错: {str(e)}", exc_info=True)
            return False

    async def _generate_additional_queries(self, original_query, results):
        """
        基于已有结果生成额外的查询以补充信息
        
        Args:
            original_query: 原始查询
            results: 已获取的结果
            
        Returns:
            list: 额外查询列表
        """
        if not results:
            return [original_query]  # 如果没有结果，返回原始查询
        
        context_text = ""
        for i, result in enumerate(results):
            if 'content' in result and result['content']:
                snippet = result['content']
                context_text += f"文档{i}: {snippet}...\n\n"
        
        prompt = PromptTemplates.format_additional_queries_prompt(original_query, context_text, self.generate_query_num)
        
        try:
            response = await self.llm_client.generate(prompt)
            queries = [q.strip() for q in response.strip().split("\n") if q.strip()]
            valid_queries = [q for q in queries if len(q.split()) <= 10 and q != original_query][:self.generate_query_num]
            if not valid_queries:
                default_queries = [
                    f"{original_query} 最新进展",
                    f"{original_query} 案例分析",
                    f"{original_query} 挑战与机遇"
                ]
                return default_queries
            return valid_queries
        except Exception as e:
            logger.error(f"生成额外查询时出错: {str(e)}", exc_info=True)
            return [
                f"{original_query} 最新研究",
                f"{original_query} 应用案例"
            ]

    async def _generate_search_queries(self, message: ChatMessage) -> List[str]:
        """
        生成搜索查询语句
        
        Args:
            message: 用户消息
        Returns:
            List[str]: 搜索查询语句列表
        """
        prompt = PromptTemplates.format_search_queries_prompt(message.message, self.generate_query_num)
        
        try:
            response = await self.llm_client.generate(prompt)
            queries = str2Json(response)
            if isinstance(queries, list):
                return queries
            else:
                logger.warning(f"搜索查询生成格式错误: {response}")
                return [message.message]
        except Exception as e:
            logger.error(f"生成搜索查询时出错: {e}", exc_info=True)
            return [message.message]

    async def _recognize_intent(self, query: str) -> str:
        """
        识别用户查询的意图，确定对应的研究场景
        
        Args:
            query: 用户查询文本
            
        Returns:
            str: 识别的场景名称
        """
        try:
            logger.info(f"识别查询意图: {query}")
            prompt = PromptTemplates.format_intent_recognition_prompt(query)
            response = await self.llm_client.generate(
                prompt=prompt,
                system_message=PromptTemplates.get_system_message()
            )
            return response.strip().lower()
        except Exception as e:
            logger.error(f"意图识别出错: {str(e)}")
            return self.crawler_config.get_default_scenario()