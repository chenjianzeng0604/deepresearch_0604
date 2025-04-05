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
from src.memory.memory_manager import memory_manager
from src.database.vectordb.milvus_dao import milvus_dao
from src.tools.crawler.crawler_config import crawler_config
from src.config.app_config import app_config
from src.app.chat_bean import ChatMessage
from src.utils.json_parser import str2Json
from src.prompts.prompt_templates import PromptTemplates
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
        self.milvus_dao = milvus_dao
        self.llm_client = llm_client
        self.crawler_manager = CrawlerManager()
        self.research_max_iterations = int(os.getenv("RESEARCH_MAX_ITERATIONS"))
        
        # 初始化数据库管理器
        try:
            self.session_manager = session_manager
            self.memory_manager = memory_manager
            # 确保会话存在
            if not self.session_manager.get_session(self.session_id):
                self.session_manager.create_session(self.session_id)
            logger.info(f"数据库管理器初始化成功，会话ID: {self.session_id}")
        except Exception as e:
            logger.error(f"数据库管理器初始化失败: {str(e)}")
            self.session_manager = None
            self.memory_manager = None
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
        self.memory_manager.save_chat_history(self.session_id, [{"role": "user", "content": query}])
        
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
            self.memory_manager.save_chat_history(self.session_id, [{"role": "assistant", "content": response_content}])
            yield {"type": "status", "content": "处理完成", "phase": "complete"}
        except Exception as e:
            logger.error(f"处理流时出错: {str(e)}", exc_info=True)
            yield {"type": "error", "content": f"处理您的查询时出错: {str(e)}"}

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
        all_content = []
        for i, result in enumerate(research_results):
            content = f"""[文章{i}]
            URL: {result['url']}
            标题: {result['title']}
            内容: {result['content']}
            """
            all_content.append(content)
        
        if all_content:
            deep_analysis_prompt = PromptTemplates.format_deep_analysis_prompt(
                query, 
                '\n'.join(all_content)
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
                            yield {"type": "content", "content": buffer, "phase": "deep_summary"}
                            buffer = ""
                    if buffer:
                        yield {"type": "content", "content": buffer, "phase": "deep_summary"}
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
        chat_history = self.memory_manager.get_chat_history(self.session_id)
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

    async def _research(self, message):
        """
        研究方法
        
        Args:
            message: 用户查询ChatMessage对象
            
        Returns:
            AsyncGenerator: 研究过程中的状态更新和最终结果
        """
        origin_query = message.message

        chat_history = self.memory_manager.get_chat_history(self.session_id)
        context=json.dumps(chat_history) if chat_history else ""
        
        all_results = []
        iteration_count = 0

        try:
            max_token_limit = self.llm_client._get_model_token_limit(self.llm_client.model)
            available_token_limit = max_token_limit - 2048
            logger.info(f"总结模型 {self.llm_client.model}的可用token限制: {available_token_limit}")
        except Exception as e:
            logger.warning(f"获取模型token限制失败: {e}，使用默认值12000")
            available_token_limit = 12000
            
        handle_fetch_url = True
        current_token_count = 0
        filter_url = set()
        while iteration_count < self.research_max_iterations:
            try:
                evaluate_result = await self._evaluate_information(origin_query, context, all_results)
                logger.info(f"评估结果{evaluate_result}")
                evaluate_query = evaluate_result["query"]

                if evaluate_result["fetch_url"] and handle_fetch_url:
                    handle_fetch_url = False
                    async for result in self.crawler_manager.web_crawler.fetch_article_stream(evaluate_result["fetch_url"], evaluate_query if evaluate_query else origin_query):
                        if 'content' in result and result['content'] and len(result['content'].strip()) > 0:
                            try:
                                result_tokens = self.llm_client.count_tokens(
                                    f"URL: {result['url']}\n标题: {result['title']}\n内容: {result['content']}"
                                )
                                if current_token_count + result_tokens > available_token_limit * 0.9:
                                    logger.info(f"添加新结果将超过token限制，当前:{current_token_count}，新结果:{result_tokens}，限制:{available_token_limit}")
                                    await self._compress_results(origin_query, all_results, result, available_token_limit)
                                    current_token_count = sum(self.llm_client.count_tokens(
                                        f"URL: {r.get('url', '')}\n标题: {r.get('title', '')}\n内容: {r.get('content', '')}"
                                    ) for r in all_results)
                                    logger.info(f"压缩后的token数: {current_token_count}")
                                
                                if current_token_count + result_tokens <= available_token_limit:
                                    filter_url.add(result['url'])
                                    all_results.append(result)
                                    current_token_count += result_tokens
                                    yield {
                                        "type": "research_process", 
                                        "result": result,
                                        "phase": "web_search"
                                    }
                            except Exception as e:
                                logger.error(f"处理搜索结果时出错: {str(e)}", exc_info=True)
                    continue
                
                if evaluate_result and evaluate_result["enough"]:
                    break
                yield {
                    "type": "research_process", 
                    "result": evaluate_result,
                    "phase": "evaluate"
                }

                if evaluate_query:
                    url_list_str = ", ".join([f"'{url}'" for url in filter_url])
                    filter_expr = None
                    if url_list_str:
                        filter_expr = f"url not in [{url_list_str}]"
                    vector_contents = self.milvus_dao.search(
                        collection_name=self.crawler_config.get_collection_name(evaluate_result["scenario"]),
                        data=self.milvus_dao.generate_embeddings([evaluate_query]),
                        filter=filter_expr,
                        limit=self.vectordb_limit,
                        output_fields=["id", "url", "title", "content", "create_time"]
                    )
                    if vector_contents:
                        unique_contents = {}
                        for contents in vector_contents:
                            if not contents or len(contents) == 0:
                                continue
                            for content in contents:
                                entity = content['entity']
                                unique_contents[entity['url']] = entity
                        news_items = list(unique_contents.values())
                        if news_items:
                            all_results.extend(news_items)
                            filter_url.update([r["url"] for r in news_items])

                search_fetch_url_list = []
                search_url_list = evaluate_result["search_url"]
                if search_url_list:
                    for search_url in search_url_list:
                        urls = await self.crawler_manager.web_crawler.parse_sub_url(search_url)
                        if urls:
                            search_fetch_url_list.extend(urls)
                search_fetch_url_list = [url for url in search_fetch_url_list if url not in filter_url]
                if search_fetch_url_list:
                    async for result in self.crawler_manager.web_crawler.fetch_article_stream(search_fetch_url_list, evaluate_query if evaluate_query else origin_query):
                        if 'content' in result and result['content'] and len(result['content'].strip()) > 0:
                            try:
                                result_tokens = self.llm_client.count_tokens(
                                    f"URL: {result['url']}\n标题: {result['title']}\n内容: {result['content']}"
                                )
                                if current_token_count + result_tokens > available_token_limit * 0.9:
                                    logger.info(f"添加新结果将超过token限制，当前:{current_token_count}，新结果:{result_tokens}，限制:{available_token_limit}")
                                    await self._compress_results(origin_query, all_results, result, available_token_limit)
                                    current_token_count = sum(self.llm_client.count_tokens(
                                        f"URL: {r.get('url', '')}\n标题: {r.get('title', '')}\n内容: {r.get('content', '')}"
                                    ) for r in all_results)
                                    logger.info(f"压缩后的token数: {current_token_count}")
                                
                                if current_token_count + result_tokens <= available_token_limit:
                                    filter_url.add(result['url'])
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
                logger.error(f"deepresearch迭代时出错: {str(e)}")
            
            if len(all_results) >= self.summary_limit:
                break
            iteration_count += 1
        
        if len(all_results) > self.summary_limit:
            all_results = all_results[:self.summary_limit]
        
        yield {"type": "research_results", "result": all_results}

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
            URL: {result['url']}
            标题: {result['title']}
            内容: {result['content']}
            """
            all_content.append(content)
        
        # 新内容信息
        new_content = f"""[新文章]
        URL: {new_result['url']}
        标题: {new_result['title']}
        内容: {new_result['content']}
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
                model=os.getenv("COMPRESSION_MODEL", self.llm_client.model)
            )
            
            # 解析压缩结果
            try:
                result_data = str2Json(compression_response)
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

    async def _evaluate_information(self, query, context, results):
        """
        使用LLM评估已获取的信息是否足够回答用户查询
        
        Args:
            query: 用户查询
            context: 历史对话上下文
            results: 已获取的结果
        Returns:
            bool: 信息是否足够
        """
        article_text = ""
        if results:
            for i, result in enumerate(results):
                if 'content' in result and result['content']:
                    snippet = result['content']
                    article_text += f"文档{i}: {snippet}...\n"
        
        prompt = PromptTemplates.format_evaluate_information_prompt(query, context, article_text)
        
        try:
            response = await self.llm_client.generate(
                prompt=prompt, 
                model=os.getenv("EVALUATE_INFORMATION_MODEL")
            )
            return str2Json(response)
        except Exception as e:
            logger.error(f"评估信息充分性时出错: {str(e)}", exc_info=True)
            return {}