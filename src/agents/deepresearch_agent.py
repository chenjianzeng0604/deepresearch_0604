"""
DeepresearchAgent - 专门用于搜索爬取相关数据进行深度研究的智能代理
"""

import logging
import asyncio
import os
import datetime
from typing import Dict, List, Any, Optional, Set, Tuple, AsyncGenerator
import uuid
import json

from src.crawler.crawler_manager import CrawlerManager
from src.utils.llm_client import LLMClient
from src.models.config import AppConfig
from src.crawler.web_crawlers import WebCrawler
from src.models.response import ChatMessage, ChatResponse
from src.utils.json_parser import str2Json
from src.vectordb.milvus_dao import MilvusDao
from src.utils.prompt_templates import PromptTemplates
from src.crawler.config import CrawlerConfig
from urllib.parse import quote
import os

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
        self.config = AppConfig.from_env()
        self.crawler_config = CrawlerConfig()
        self.session_id = session_id
        self.summary_limit = int(os.getenv("SUMMARY_LIMIT"))
        self.vectordb_limit = int(os.getenv("VECTORDB_LIMIT"))
        self.generate_query_num = int(os.getenv("GENERATE_QUERY_NUM"))
        self.milvus_dao = MilvusDao(
            uri=os.getenv("MILVUS_URI", "http://localhost:19530"),
            user=os.getenv("MILVUS_USER", ""),
            password=os.getenv("MILVUS_PASSWORD", ""),
            db_name=os.getenv("MILVUS_DB_NAME", "default"),
            reconnect_attempts=int(os.getenv("MILVUS_RECONNECT_ATTEMPTS", "3")),
            reconnect_delay=int(os.getenv("MILVUS_RECONNECT_DELAY", "2"))
        )
        self.llm_client = LLMClient(api_key=self.config.llm.api_key, 
                                        model=self.config.llm.model, 
                                        api_base=self.config.llm.api_base)
        self.crawler_manager = CrawlerManager()
        self.research_max_iterations = int(os.getenv("RESEARCH_MAX_ITERATIONS"))
    
    async def process_stream(self, message, **kwargs):
        """
        流式处理用户查询，逐步返回处理结果
        
        Args:
            message: 用户查询ChatMessage对象
            **kwargs: 其他参数
            
        Returns:
            AsyncGenerator[Dict[str, Any], None]: 处理结果流
        """
        research_results = await self._research(message)
        async for chunk in self._generate_response_stream(message, research_results):
            if isinstance(chunk, str):
                yield {"type": "content", "content": chunk}
            else:
                yield chunk
    
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
            scenario = response.strip().lower()
            if scenario in self.crawler_config.supported_scenarios:
                logger.info(f"查询 '{query}' 识别为场景: {scenario}")
                return scenario
            else:
                logger.warning(f"意图识别返回了不支持的场景: {scenario}，使用默认场景")
                return self.crawler_config.default_scenario
        except Exception as e:
            logger.error(f"意图识别出错: {str(e)}")
            return self.crawler_config.default_scenario
    
    async def _research(self, message):
        """
        执行研究，优先从Milvus迭代查询获取数据，间歇性使用搜索引擎补充
        
        Args:
            message: 用户查询ChatMessage对象
            
        Returns:
            研究结果
        """
        all_results = []
        scenario = await self._recognize_intent(message.message)
        collection_name = self.crawler_config.get_collection_name(scenario)
            
        logger.info(f"为查询 '{message.message}' 使用场景 '{scenario}', 集合 '{collection_name}'")
        
        refined_queries = await self._generate_search_queries(message)
        all_queries_used = set(refined_queries)
        all_urls_seen = set()
        
        max_iterations = self.research_max_iterations
        current_iteration = 0

        while current_iteration < max_iterations:
            current_iteration += 1
            logger.info(f"开始第 {current_iteration}/{max_iterations} 轮信息检索")
            try:
                iteration_results = []
            
                if collection_name:
                    milvus_contents = self.milvus_dao.search(
                        collection_name=collection_name,
                        data=self.milvus_dao.generate_embeddings(refined_queries),
                        limit=self.vectordb_limit,
                        output_fields=["id", "url", "content", "create_time"]
                    )
                    
                    milvus_unique_contents = {}
                    temp_urls_seen = set()
                    for query_contents in milvus_contents:
                        if not query_contents:
                            continue
                        for contents in query_contents:
                            entity = contents['entity']
                            if (isinstance(entity, dict) and 
                                'content' in entity and 
                                entity['content'] and 
                                len(entity['content'].strip()) > 0 and 
                                'url' in entity and 
                                entity['url'] not in all_urls_seen):
                                milvus_unique_contents[entity['url']] = entity
                                temp_urls_seen.add(entity['url'])
                        all_urls_seen.update(temp_urls_seen)
                        temp_urls_seen.clear()
                    
                    milvus_results = list(milvus_unique_contents.values())
                    if milvus_results:
                        iteration_results.extend(milvus_results)
                        logger.info(f"从Milvus知识库集合 {collection_name} 获取到 {len(milvus_results)} 条新结果")

                tasks = []
                for query in refined_queries:
                    try:
                        logger.info(f"使用搜索引擎获取文章: {query}")
                        search_url_formats = self.crawler_config.get_search_url_formats('online_search')
                        for search_engine, search_url_format in search_url_formats.items():
                            try:
                                encoded_query = quote(query)
                                search_url = search_url_format.format(encoded_query)
                                logger.info(f"从 {search_engine} 获取 '{query}' 相关文章，URL: {search_url}")
                                web_crawler = self.crawler_manager.web_crawler
                                links = await web_crawler.parse_sub_url(search_url)
                                if not links:
                                    logger.warning(f"无法从 {search_url} 获取文章链接: {query}")
                                    continue
                                links = [link for link in links if link not in all_urls_seen]
                                all_urls_seen.update(links)
                                task = asyncio.create_task(web_crawler.fetch_article(links))
                                tasks.append(task)
                                logger.info(f"为查询 '{query}' 找到 {len(links)} 个新链接")
                            except Exception as e:
                                logger.error(f"从 {search_engine} 获取文章时出错: {str(e)}")
                    except Exception as e:
                        logger.error(f"使用搜索引擎搜索获取文章时出错: {query}, {str(e)}")
                
                if tasks:
                    try:
                        search_contents = await asyncio.gather(*tasks, return_exceptions=True)
                        if search_contents:
                            search_unique_contents = {}
                            for result in search_contents:
                                if result is not None and \
                                    (isinstance(result, dict) and 
                                    'content' in result and 
                                    result['content'] and 
                                    len(result['content'].strip()) > 0 and 
                                    'url' in result and 
                                    result['url'] not in all_urls_seen):
                                    search_unique_contents[result['url']] = result
                                    all_urls_seen.add(result['url'])
                            search_results = list(search_unique_contents.values())
                            if search_results:
                                iteration_results.extend(search_results)
                                web_crawler.save_article(search_results, scenario)
                                logger.info(f"从搜索引擎获取到 {len(search_results)} 条新结果")
                    except Exception as e:
                        logger.error(f"爬取搜索结果时出错: {str(e)}", exc_info=True)
                
                if iteration_results:
                    all_results.extend(iteration_results)
                    logger.info(f"第 {current_iteration} 轮新增 {len(iteration_results)} 条结果，总计 {len(all_results)} 条")
                else:
                    logger.warning(f"第 {current_iteration} 轮未获取到新结果")
                
                if not all_results and current_iteration >= 2:
                    logger.warning("多次迭代后仍未找到相关结果，提前结束检索")
                    break

                if len(all_results) > 0:
                    is_sufficient = await self._evaluate_information_sufficiency(message.message, all_results)
                    
                    if is_sufficient:
                        logger.info(f"LLM评估信息已足够，停止迭代")
                        break
                    
                    if current_iteration < max_iterations:
                        additional_queries = await self._generate_additional_queries(message.message, all_results)
                        additional_queries = [q for q in additional_queries if q not in all_queries_used]
                        if additional_queries:
                            all_queries_used.update(additional_queries)
                            refined_queries = additional_queries
                            logger.info(f"生成 {len(refined_queries)} 个新查询继续检索: {refined_queries}")
                        else:
                            logger.info("无法生成新的查询，将使用最初查询继续检索")
            except Exception as e:
                logger.error(f"第 {current_iteration} 轮检索出错: {str(e)}", exc_info=True)
        
        logger.info(f"研究结束，共收集 {len(all_results)} 条结果")
        
        for result in all_results:
            if "scenario" not in result or not result["scenario"]:
                result["scenario"] = scenario
                
        return {
            "query": message.message,
            "results": all_results,
            "count": len(all_results)
        }
    
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
            
        # 准备上下文信息
        context_text = ""
        for i, result in enumerate(results[:10], 1):  # 只使用前10个结果评估，避免过长
            if 'content' in result and result['content']:
                snippet = result['content'][:1000]  # 取内容前1000个字符
                context_text += f"文档{i}: {snippet}...\n\n"
        
        # 使用模板构建提示词
        prompt = PromptTemplates.format_information_sufficiency_prompt(query, context_text)
        
        try:
            response = await self.llm_client.generate(prompt)
            
            # 判断回复中是否包含SUFFICIENT
            if "SUFFICIENT" in response.strip().upper():
                return True
            return False
        except Exception as e:
            logger.error(f"评估信息充分性时出错: {str(e)}", exc_info=True)
            # 出错时默认为不足，继续搜索
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
        for i, result in results:
            if 'content' in result and result['content']:
                snippet = result['content']
                context_text += f"文档{i}: {snippet}...\n\n"
        
        # 使用模板构建提示词
        prompt = PromptTemplates.format_additional_queries_prompt(original_query, context_text, self.generate_query_num)
        
        try:
            response = await self.llm_client.generate(prompt)
            
            # 解析响应获取查询列表
            queries = [q.strip() for q in response.strip().split("\n") if q.strip()]
            
            # 过滤并限制查询数量
            valid_queries = [q for q in queries if len(q.split()) <= 10 and q != original_query][:5]
            
            if not valid_queries:
                # 如果没有有效查询，使用默认策略生成
                default_queries = [
                    f"{original_query} 最新进展",
                    f"{original_query} 案例分析",
                    f"{original_query} 挑战与机遇"
                ]
                return default_queries
                
            return valid_queries
        except Exception as e:
            logger.error(f"生成额外查询时出错: {str(e)}", exc_info=True)
            # 出错时返回简单变形的原始查询
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
            # 调用LLM生成搜索查询
            response = await self.llm_client.generate(prompt)

            # 解析JSON响应
            queries = str2Json(response)
            
            # 确保返回列表类型
            if isinstance(queries, list):
                return queries
            else:
                logger.warning(f"搜索查询生成格式错误: {response}")
                # 返回基本查询
                return [message.message]
                
        except Exception as e:
            logger.error(f"生成搜索查询时出错: {e}", exc_info=True)
            # 出错时使用原始消息作为查询
            return [message.message]
    
    async def _generate_response_stream(self, message, research_results):
        """
        生成流式响应
        
        Args:
            message: 用户查询ChatMessage对象
            research_results: 研究结果
            
        Returns:
            流式响应生成器
        """
        # 提取查询文本
        query = message.message
        
        try:
            results = research_results.get("results", [])
            if results:
                all_summaries = []
                all_summaries.extend([result['content'] for result in results if 'content' in result])
                if all_summaries:
                    deep_analysis_prompt = PromptTemplates.format_deep_analysis_prompt(query, '\n\n'.join(all_summaries))
                    async for chunk in self.llm_client.generate_with_streaming(deep_analysis_prompt):
                        yield chunk
            else:
                yield f"抱歉，我没有找到关于'{query}'的相关信息。请尝试其他查询或更广泛的话题。"
        except Exception as e:
            logger.error(f"生成流式响应时出错: {str(e)}", exc_info=True)
            yield f"抱歉，处理您的查询'{query}'时遇到错误。错误详情: {str(e)}"