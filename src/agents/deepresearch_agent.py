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
from urllib.parse import quote

logger = logging.getLogger(__name__)

class DeepresearchAgent:
    """
    专门用于搜索爬取相关数据进行深度研究的智能代理
    """
    
    def __init__(self, session_id: str = None, config: Optional[AppConfig] = None):
        """
        初始化深度研究智能代理
        
        Args:
            session_id: 会话ID
            config: 代理配置
        """
        session_id = session_id or str(uuid.uuid4())
        self.config = config or {}
        self.session_id = session_id
        self.summary_limit = 100
        self._initialized = False
        self.milvus_dao = MilvusDao("deepresearch_collection_v2")
    
    async def _init_components(self):
        """初始化组件，这是一个异步方法"""
        try:
            logger.info("初始化科技新闻代理组件...")
            
            # 初始化LLM客户端
            import os
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key and hasattr(self.config, 'llm') and hasattr(self.config.llm, 'api_key'):
                api_key = self.config.llm.api_key
                
            if not api_key:
                raise ValueError("缺少 OpenAI API Key，请在环境变量 OPENAI_API_KEY 中设置或在配置中提供")
                
            model = os.environ.get("LLM_MODEL", "gpt-4-turbo-preview")
            if hasattr(self.config, 'llm') and hasattr(self.config.llm, 'model'):
                model = self.config.llm.model

            api_base = os.getenv("LLM_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            if not api_base and hasattr(self.config, 'llm') and hasattr(self.config.llm, 'api_base'):
                api_base = self.config.llm.api_base
                
            self.llm_client = LLMClient(api_key=api_key, model=model, api_base=api_base)
            self.crawler_manager = CrawlerManager()

            self.web_searcher = WebSearcher(
                api_key=self.config.search.api_key,
                config=self.config.search
            )
            
            self._initialized = True

            logger.info("科技新闻代理组件初始化完成")
        except Exception as e:
            logger.error(f"初始化科技新闻代理组件时出错: {str(e)}", exc_info=True)
            raise
    
    async def process_stream(self, message, **kwargs):
        """
        流式处理用户查询，逐步返回处理结果
        
        Args:
            message: 用户查询ChatMessage对象
            **kwargs: 其他参数
            
        Returns:
            AsyncGenerator[Dict[str, Any], None]: 处理结果流
        """
        # 确保组件已初始化
        if not self._initialized:
            await self._init_components()
        
        # 研究
        research_results = await self._research(message)
        
        # 生成流式回复
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
        refined_queries = await self._generate_search_queries(message)
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
                            tasks.append(web_crawler.fetch_article_and_save2milvus(links))

                    if "web_site" in platforms and self.crawler_manager.config.search_url and len(self.crawler_manager.config.search_url) > 0:
                        tasks.append(web_crawler.fetch_article_and_save2milvus(self.crawler_manager.config.search_url))
                    
                    if "github" in platforms:
                        github_crawler = self.crawler_manager.github_crawler
                        links = await github_crawler.parse_sub_url(query)
                        if not links:
                            logger.warning(f"无法从 GitHub 获取仓库: {query}")
                            continue
                        all_links.extend(links)
                        tasks.append(github_crawler.fetch_article_and_save2milvus(links))

                    if "arxiv" in platforms:
                        arxiv_crawler = self.crawler_manager.arxiv_crawler
                        links = await arxiv_crawler.parse_sub_url(query)
                        if not links:
                            logger.warning(f"无法从 arXiv 获取文章: {query}")
                            continue
                        all_links.extend(links)
                        tasks.append(arxiv_crawler.fetch_article_and_save2milvus(links))

                    if "weibo" in platforms:
                        weibo_crawler = self.crawler_manager.weibo_crawler
                        links = await weibo_crawler.parse_sub_url(query)
                        if not links:
                            logger.warning(f"无法从微博获取文章: {query}")
                            continue
                        all_links.extend(links)
                        tasks.append(weibo_crawler.fetch_article_and_save2milvus(links))

                    if "weixin" in platforms:
                        wechat_crawler = self.crawler_manager.wechat_crawler
                        links = await wechat_crawler.parse_sub_url(query)
                        if not links:
                            logger.warning(f"无法从微信获取文章: {query}")
                            continue
                        all_links.extend(links)
                        tasks.append(wechat_crawler.fetch_article_and_save2milvus(links))

                    if "twitter" in platforms:
                        twitter_crawler = self.crawler_manager.twitter_crawler
                        links = await twitter_crawler.parse_sub_url(query)
                        if not links:
                            logger.warning(f"无法从 Twitter 获取推文: {query}")
                            continue
                        all_links.extend(links)
                        tasks.append(twitter_crawler.fetch_article_and_save2milvus(links))
                        
                    if "search" in platforms:
                        try:
                            logger.info(f"使用WebSearcher搜索获取文章: {query}")
                            search_results = await self.web_searcher.search(query)
                            if not search_results:
                                logger.warning(f"无法通过WebSearcher获取搜索结果: {query}")
                                continue
                                
                            # 从搜索结果中提取链接
                            search_links = []
                            for result in search_results:
                                if "link" in result and result["link"]:
                                    search_links.append(result["link"])
                                elif "url" in result and result["url"]:
                                    search_links.append(result["url"])
                            
                            if search_links:
                                all_links.extend(search_links)
                                tasks.append(self.crawler_manager.web_crawler.fetch_article_and_save2milvus(search_links))
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
                output_fields=["id", "url", "content"],
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
        prompt = f"""
        请根据以下用户问题，生成10个相关的查询语句，每个查询语句要求：
        1. 保留原来的用户问题，并放在第一个位置
        2. 足够精确，能够找到与用户需求最相关的内容。
        3. 涵盖商业模式、产品调研、软件工程实践、应用案例等。
        4. 问题不能重复，并且要有利于联网搜索和大模型识别
        5. 问题不要带时间，避免大模型知识过时导致搜索过期的数据
        
        用户问题: {message.message}
        
        请以JSON数组格式返回查询语句，例如:
        ["查询语句1", "查询语句2", "查询语句3"]
        
        仅返回JSON格式结果，不要包含其他文本。
        """
        
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
            # 从研究结果生成响应
            results = research_results.get("results", [])
            
            if not results:
                yield f"抱歉，我没有找到关于'{query}'的相关信息。请尝试其他查询或更广泛的话题。"
                return
            
            # 收集所有文章摘要，以便后续生成综合分析
            all_summaries = []

            split_results = [results[i:i+2] for i in range(0, len(results), 2)]

            for split_result in split_results:
                # 构建摘要分析提示
                contents = []
                for result in split_result:
                    if "content" in result:
                        contents.append(result['content'])
                    else:
                        logger.warning(f"文章内容格式错误: {result}")
                try:
                    summary_analysis_prompt = f"""
                        基于以下关于"{query}"的多篇文章，提炼出核心思想与关键要点，不超过1000字，文章内容:
                        {' '.join(contents)}
                        """
                except Exception as e:
                   logger.error(f"获取总结拆分文章的提示词时出错: {str(e)}", exc_info=True)
                   continue
                try:
                    summary = await self.llm_client.generate(summary_analysis_prompt)
                    logger.info(f"生成摘要: {summary}")
                    all_summaries.append(summary)
                except Exception as e:
                    logger.error(f"生成摘要时出错: {str(e)}", exc_info=True)
                    continue
            
            # 所有文章摘要都已流式输出，现在生成对所有摘要的综合分析
            if all_summaries:
                yield "\n\n## 综合分析与见解\n\n"
                
                # 构建综合分析提示
                deep_analysis_prompt = f"""
                    基于以下关于"{query}"的多篇文章摘要，提供一个深度的综合分析。分析应该:
                    1. 罗列摘要核心思想和关键信息
                    2. 分析商业模式与产品亮点
                    3. 分析应用案例
                    4. 软件工程实践方式
                    5. 提供整体见解和结论

                    摘要内容:
                    {' '.join(all_summaries)}

                    请提供全面而深入的分析，重点关注信息的融合和见解，而不是简单重复摘要内容。
                    """
                
                async for chunk in self.llm_client.generate_with_streaming(deep_analysis_prompt):
                    yield chunk
                
        except Exception as e:
            logger.error(f"生成流式响应时出错: {str(e)}", exc_info=True)
            yield f"抱歉，处理您的查询'{query}'时遇到错误。错误详情: {str(e)}"