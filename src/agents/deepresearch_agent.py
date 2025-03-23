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
        self.generate_query_num = int(os.getenv("GENERATE_QUERY_NUM"))
        self.milvus_dao = MilvusDao(os.getenv("DEEPRESEARCH_COLLECTION"))
        self.llm_client = LLMClient(api_key=self.config.llm.api_key, 
                                        model=self.config.llm.model, 
                                        api_base=self.config.llm.api_base)
        self.crawler_manager = CrawlerManager()
        self.web_searcher = WebSearcher(
            api_key=self.config.search.api_key,
            config=self.config.search
        )
    
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
        执行研究
        
        Args:
            message: 用户查询ChatMessage对象
            
        Returns:
            研究结果
        """
        if self.generate_query_num > 1:
            refined_queries = await self._generate_search_queries(message)
        else:
            refined_queries = [message.message]
        all_results = []
        try:    
            # 创建并发任务列表
            all_links = []
            tasks = []
            platforms = message.metadata["platforms"]

            for query in refined_queries:
                logger.info(f"正在获取爬虫内容: {query}")
                try:
                    if "web_site" in platforms:
                        web_crawler = self.crawler_manager.web_crawler
                        for search_url_format in self.crawler_manager.config.search_url_formats.values():
                            search_url = search_url_format.format(quote(query))
                            links = await web_crawler.parse_sub_url(search_url)
                            if not links:
                                logger.warning(f"无法从 {search_url} 获取文章: {query}")
                                continue
                            all_links.extend(links)
                            tasks.append(web_crawler.fetch_article_and_save2milvus(query, links))

                    if "web_site" in platforms and self.crawler_manager.config.search_url and len(self.crawler_manager.config.search_url) > 0:
                        tasks.append(web_crawler.fetch_article_and_save2milvus(query, self.crawler_manager.config.search_url))
                    
                    if "github" in platforms:
                        github_crawler = self.crawler_manager.github_crawler
                        links = await github_crawler.parse_sub_url(query)
                        if not links:
                            logger.warning(f"无法从 GitHub 获取仓库: {query}")
                        else:
                            all_links.extend(links)
                            tasks.append(github_crawler.fetch_article_and_save2milvus(query, links))

                    if "arxiv" in platforms:
                        arxiv_crawler = self.crawler_manager.arxiv_crawler
                        links = await arxiv_crawler.parse_sub_url(query)
                        if not links:
                            logger.warning(f"无法从 arXiv 获取文章: {query}")
                        else:
                            all_links.extend(links)
                            tasks.append(arxiv_crawler.fetch_article_and_save2milvus(query, links))

                    if "weixin" in platforms:
                        wechat_crawler = self.crawler_manager.wechat_crawler
                        links = await wechat_crawler.parse_sub_url(query)
                        if not links:
                            logger.warning(f"无法从微信获取文章: {query}")
                        else:
                            all_links.extend(links)
                            tasks.append(wechat_crawler.fetch_article_and_save2milvus(query, links))

                    if "search" in platforms:
                        try:
                            logger.info(f"使用WebSearcher搜索获取文章: {query}")
                            search_results = await self.web_searcher.search(query)
                            if not search_results:
                                logger.warning(f"无法通过WebSearcher获取搜索结果: {query}")
                            else:
                                links = []
                                for result in search_results:
                                    if "link" in result and result["link"]:
                                        links.append(result["link"])
                                if links:
                                    all_links.extend(links)
                                    tasks.append(self.crawler_manager.web_crawler.fetch_article_and_save2milvus(query, links))
                                else:
                                    logger.warning(f"搜索结果中没有有效链接: {query}")
                        except Exception as e:
                            logger.error(f"使用WebSearcher搜索获取文章时出错: {query}, {str(e)}", exc_info=True)
                except Exception as e:
                    logger.error(f"获取爬虫内容时出错: {query}, {str(e)}", exc_info=True)
                
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                logger.error(f"获取爬虫内容时出错: {str(e)}", exc_info=True)

            url_list_str = ", ".join([f"'{url}'" for url in all_links])
            filter_expr = f"url in [{url_list_str}]"
            all_contents = self.milvus_dao._search(
                collection_name=self.milvus_dao.collection_name,
                data=self.milvus_dao._generate_embeddings(refined_queries),
                filter=filter_expr,
                limit=self.summary_limit,
                output_fields=["id", "url", "content", "create_time"],
                order_by="create_time desc"
            )
            unique_contents = {}
            for query_contents in all_contents:
                if not query_contents:
                    continue
                for contents in query_contents:
                    entity = contents['entity']
                    if isinstance(entity, dict) and 'content' in entity and entity['content'] and len(entity['content'].strip()) > 0 and 'url' in entity and entity['url'] not in unique_contents:
                        unique_contents[entity['url']] = entity
            
            news_items = list(unique_contents.values())
            if news_items:
                all_results.extend(news_items)

        except Exception as e:
            logger.error(f"获取爬虫内容时出错: {str(e)}", exc_info=True)

        return {
            "query": message.message,
            "results": all_results,
            "count": len(all_results)
        }

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