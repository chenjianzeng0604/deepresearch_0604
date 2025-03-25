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
from src.search.web_searcher import WebSearcher
from src.utils.llm_client import LLMClient
from src.models.config import AppConfig
from src.crawler.web_crawlers import WebCrawler
from src.models.response import ChatMessage, ChatResponse
from src.utils.json_parser import str2Json
from src.vectordb.milvus_dao import MilvusDao
from src.utils.prompt_templates import PromptTemplates
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
        self.web_searcher = WebSearcher(
            api_key=self.config.search.api_key,
            config=self.config.search
        )
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
    
    async def _research(self, message):
        """
        执行研究，优先从Milvus迭代查询获取数据，间歇性使用搜索引擎补充
        
        Args:
            message: 用户查询ChatMessage对象
            
        Returns:
            研究结果
        """
        all_results = []
        refined_queries = await self._generate_search_queries(message)
        all_queries_used = set(refined_queries)  # 记录已使用过的查询词
        all_urls_seen = set()  # 避免重复处理同一URL
        
        max_iterations = self.research_max_iterations
        current_iteration = 0
        min_results_threshold = self.summary_limit
        search_interval = 2

        while current_iteration < max_iterations:
            current_iteration += 1
            logger.info(f"开始第 {current_iteration}/{max_iterations} 轮信息检索")
            
            try:
                iteration_results = []

                search_links = []
                if current_iteration == 1 or (current_iteration % search_interval == 0 and len(all_results) < min_results_threshold):
                    logger.info(f"第 {current_iteration} 轮: 使用搜索引擎补充数据")
                    tasks = []
                    
                    for query in refined_queries[:2]:
                        try:
                            logger.info(f"使用WebSearcher搜索获取文章: {query}")
                            search_results = await self.web_searcher.search(query)
                            if search_results:
                                links = []
                                for result in search_results:
                                    if "link" in result and result["link"] and result["link"] not in all_urls_seen:
                                        links.append(result["link"])
                                        all_urls_seen.add(result["link"])
                                        
                                if links:
                                    search_links.extend(links)
                                    tasks.append(self.crawler_manager.web_crawler.fetch_article_and_save2milvus(query, links))
                                    logger.info(f"为查询 '{query}' 找到 {len(links)} 个新链接")
                                else:
                                    logger.warning(f"搜索结果中没有新的有效链接: {query}")
                            else:
                                logger.warning(f"无法通过WebSearcher获取搜索结果: {query}")
                        except Exception as e:
                            logger.error(f"使用WebSearcher搜索获取文章时出错: {query}, {str(e)}")
                    
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
                                        result['url'] not in [item.get('url') for item in all_results] and
                                        result['url'] not in [item.get('url') for item in iteration_results]):
                                        search_unique_contents[result['url']] = result
                                iteration_results.extend(search_unique_contents.values())

                                search_results = list(search_unique_contents.values())
                                if search_results:
                                    iteration_results.extend(search_results)
                                    logger.info(f"从搜索引擎获取到 {len(search_results)} 条新结果")
                        except Exception as e:
                            logger.error(f"爬取搜索结果时出错: {str(e)}", exc_info=True)

                milvus_contents = self.milvus_dao.search(
                    collection_name=os.getenv("DEEPRESEARCH_COLLECTION"),
                    data=self.milvus_dao.generate_embeddings(refined_queries),
                    limit=self.vectordb_limit,
                    output_fields=["id", "url", "content", "create_time"]
                )
                
                milvus_unique_contents = {}
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
                            entity['url'] not in [item.get('url') for item in all_results] and
                            entity['url'] not in [item.get('url') for item in iteration_results]):
                            milvus_unique_contents[entity['url']] = entity
                
                milvus_results = list(milvus_unique_contents.values())
                if milvus_results:
                    iteration_results.extend(milvus_results)
                    logger.info(f"从Milvus知识库获取到 {len(milvus_results)} 条新结果")
                
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
                            refined_queries = list(refined_queries)[:1]
                
                if iteration_results:
                    all_results.extend(iteration_results)
                    logger.info(f"第 {current_iteration} 轮新增 {len(iteration_results)} 条结果，总计 {len(all_results)} 条")
                else:
                    logger.warning(f"第 {current_iteration} 轮未获取到新结果")
                
                if not all_results and current_iteration >= 2:
                    logger.warning("多次迭代后仍未找到相关结果，提前结束检索")
                    break
            except Exception as e:
                logger.error(f"第 {current_iteration} 轮检索出错: {str(e)}", exc_info=True)
        
        logger.info(f"完成研究，共获取 {len(all_results)} 条结果")
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
            plan: 规划步骤
            
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