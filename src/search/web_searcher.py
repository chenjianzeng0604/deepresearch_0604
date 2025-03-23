import logging
from typing import List, Dict, Any, Optional
import json
import re
import requests
import time
import aiohttp
import asyncio

# 尝试导入网络搜索库
try:
    from duckduckgo_search import DDGS
    DUCKDUCKGO_AVAILABLE = True
except ImportError:
    DUCKDUCKGO_AVAILABLE = False

from src.models.config import SearchConfig

logger = logging.getLogger(__name__)


class WebSearcher:
    """网络搜索组件，负责执行网络搜索并处理结果"""
    
    def __init__(self, api_key: Optional[str] = None, config: SearchConfig = None):
        self.api_key = api_key
        self.config = config or SearchConfig()
        self.search_engine = self.config.search_engine.lower()
    
    async def search(self, query: str) -> List[Dict[str, Any]]:
        """
        执行网络搜索
        
        Args:
            query: 搜索查询
            
        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        logger.info(f"执行网络搜索: {query}")
        
        # 优化查询，添加招投标相关关键词
        optimized_query = self._optimize_query(query)
        
        # 根据配置选择搜索引擎
        if self.search_engine == "bing":
            return await self._search_bing(optimized_query)
        elif self.search_engine == "google":
            return await self._search_google(optimized_query)
        elif self.search_engine == "duckduckgo":
            return await self._search_duckduckgo(optimized_query)
        else:
            logger.warning(f"不支持的搜索引擎: {self.search_engine}，返回空结果")
            return []
            
    async def _search_google(self, query: str) -> List[Dict[str, Any]]:
        """
        使用Google搜索API进行搜索
        
        Args:
            query: 搜索查询
            
        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        try:
            # 使用Google Custom Search API
            logger.info(f"使用Google Custom Search API搜索: {query}")
            
            # 检查API密钥是否已设置
            if not self.api_key:
                logger.warning("未设置Google API密钥，尝试使用备用搜索引擎")
                # 尝试使用备用搜索引擎
                try:
                    return await self._search_duckduckgo(query)
                except Exception as e:
                    logger.error(f"备用搜索引擎也失败: {e}")
                    return self._generate_placeholder_results(query)
            
            # 构建API请求URL
            base_url = "https://google.serper.dev/search"
            headers = {
                'X-API-KEY': self.api_key,
                'Content-Type': 'application/json'
            }
            payload = json.dumps({
                'q': query
            })
            
            # 发送API请求，使用更强大的错误处理
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    timeout = aiohttp.ClientTimeout(total=10)  # 10秒超时
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.post(base_url, headers=headers, data=payload) as response:
                            if response.status == 200:
                                data = await response.json()
                                
                                results = []
                                
                                # 处理有机搜索结果
                                if 'organic' in data:
                                    for item in data['organic']:
                                        result = {
                                            'title': item.get('title', ''),
                                            'snippet': item.get('snippet', ''),
                                            'url': item.get('link', ''),
                                            'position': item.get('position', 0),
                                            'source': 'Google Search'
                                        }
                                        results.append(result)
                                
                                logger.info(f"成功获取Google搜索结果: {len(results)} 条")
                                return results
                            else:
                                logger.error(f"Google API响应错误: {response.status}")
                                # 最后一次尝试失败，尝试其他方法
                                if attempt == max_retries - 1:
                                    break
                                await asyncio.sleep(1)  # 等待一秒后重试
                
                except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
                    logger.error(f"连接Google API时发生错误 (尝试 {attempt+1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)  # 等待一秒后重试
                except Exception as e:
                    logger.error(f"调用Google API时发生未知错误: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)  # 等待一秒后重试
            
            # 所有重试都失败，尝试使用备用搜索引擎
            logger.warning("Google API搜索失败，尝试使用备用搜索引擎")
            try:
                return await self._search_duckduckgo(query)
            except Exception as e:
                logger.error(f"备用搜索引擎也失败: {e}")
                return self._generate_placeholder_results(query)
                
        except Exception as e:
            logger.error(f"Google搜索过程中发生错误: {e}")
            # 尝试备用方案
            try:
                return await self._search_duckduckgo(query)
            except Exception as backup_e:
                logger.error(f"备用搜索也失败: {backup_e}")
                return self._generate_placeholder_results(query)
    
    def _generate_placeholder_results(self, query: str) -> List[Dict[str, Any]]:
        """
        生成占位符搜索结果，确保即使所有搜索方法都失败也能返回一些基本信息
        
        Args:
            query: 搜索查询
            
        Returns:
            List[Dict[str, Any]]: 占位符搜索结果列表
        """
        logger.warning(f"生成搜索占位符结果: {query}")
        # 创建一个基本的占位符结果
        return [
            {
                'title': f"搜索结果: {query}",
                'snippet': "无法连接到搜索服务。这是一个占位符结果，用于确保应用程序可以继续运行。",
                'url': "https://example.com/search",
                'position': 1,
                'source': 'Placeholder',
                'content': f"无法获取关于'{query}'的搜索结果。可能的原因包括网络连接问题或搜索API服务不可用。"
                         f"这是一个占位符内容，用于确保应用程序能够继续处理而不会因为搜索失败而完全中断。"
            }
        ]
    
    async def _search_duckduckgo(self, query: str) -> List[Dict[str, Any]]:
        """
        使用DuckDuckGo搜索
        
        Args:
            query: 搜索查询
            
        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        if not DUCKDUCKGO_AVAILABLE:
            logger.error("无法使用DuckDuckGo搜索，缺少duckduckgo_search库")
            return []
        
        try:
            logger.info(f"使用DuckDuckGo搜索: {query}")
            
            results = []
            
            # 设置重试参数
            max_retries = 3
            retry_count = 0
            ddgs_results = []
            
            while retry_count < max_retries and not ddgs_results:
                try:
                    with DDGS() as ddgs:
                        # 使用API的text方法搜索
                        for r in ddgs.text(
                            query,
                            region="wt-wt",
                            safesearch="moderate",
                            timelimit="m",  # 最近一个月的结果
                            max_results=self.config.max_results
                        ):
                            ddgs_results.append(r)
                        
                except Exception as e:
                    logger.info(f"使用默认后端搜索失败: {e}")
                    
                    # 尝试使用html后端
                    try:
                        with DDGS() as ddgs:
                            for r in ddgs.text(
                                query,
                                backend="html",
                                region="wt-wt",
                                safesearch="moderate",
                                timelimit="m",
                                max_results=self.config.max_results
                            ):
                                ddgs_results.append(r)
                    except Exception as e:
                        logger.info(f"使用html后端搜索失败: {e}")
                        
                        # 尝试使用lite后端
                        try:
                            with DDGS() as ddgs:
                                for r in ddgs.text(
                                    query,
                                    backend="lite",
                                    region="wt-wt",
                                    safesearch="moderate",
                                    timelimit="m",
                                    max_results=self.config.max_results
                                ):
                                    ddgs_results.append(r)
                        except Exception as e:
                            logger.info(f"使用lite后端搜索失败: {e}")
                
                # 增加重试次数并等待
                if not ddgs_results:
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.info(f"重试DuckDuckGo搜索 ({retry_count}/{max_retries})...")
                        await asyncio.sleep(2 * retry_count)  # 指数退避策略
            
            # 处理搜索结果
            if ddgs_results:
                for i, result in enumerate(ddgs_results):
                    # 计算相关性得分
                    relevance = self._calculate_relevance(query, result.get("title", "") + " " + result.get("body", ""))
                    
                    # 创建结果项
                    results.append({
                        "title": result.get("title", ""),
                        "link": result.get("href", ""),
                        "snippet": result.get("body", ""),
                        "source": "DuckDuckGo",
                        "relevance": relevance,
                        "position": i + 1
                    })
            
            # 按相关性排序
            if results:
                results.sort(key=lambda x: x["relevance"], reverse=True)
            
            return results
        
        except Exception as e:
            logger.error(f"DuckDuckGo搜索出错: {e}", exc_info=True)
            return []
    
    async def _search_bing(self, query: str) -> List[Dict[str, Any]]:
        """
        使用Bing搜索API
        
        Args:
            query: 搜索查询
            
        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        try:
            logger.info(f"使用Bing搜索API: {query}")
            
            # 检查API密钥是否已设置
            if not self.api_key:
                logger.error("未设置Bing API密钥，无法执行搜索")
                return []
            
            # Bing Search API V7 端点
            endpoint = "https://api.bing.microsoft.com/v7.0/search"
            
            # 设置请求头和参数
            headers = {
                "Ocp-Apim-Subscription-Key": self.api_key
            }
            
            params = {
                "q": query,
                "count": min(50, self.config.max_results),  # Bing API支持最多50个结果
                "offset": 0,
                "mkt": "zh-CN",  # 可根据需要更改市场和语言
                "freshness": "Month"  # 最近一个月的内容
            }
            
            # 发送API请求
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, headers=headers, params=params) as response:
                    if response.status != 200:
                        logger.error(f"Bing API响应错误: {response.status}")
                        return []
                    
                    data = await response.json()
            
            results = []
            
            # 处理API响应
            if "webPages" in data and "value" in data["webPages"]:
                web_pages = data["webPages"]["value"]
                
                for i, page in enumerate(web_pages):
                    # 提取搜索结果信息
                    title = page.get("name", "")
                    link = page.get("url", "")
                    snippet = page.get("snippet", "")
                    
                    # 计算相关性得分
                    relevance = self._calculate_relevance(query, title + " " + snippet)
                    
                    # 创建结果项
                    results.append({
                        "title": title,
                        "link": link,
                        "snippet": snippet,
                        "source": "Bing",
                        "relevance": relevance,
                        "position": i + 1
                    })
                
                # 按相关性排序
                results.sort(key=lambda x: x["relevance"], reverse=True)
            
            return results
            
        except Exception as e:
            logger.error(f"Bing搜索出错: {e}", exc_info=True)
            return []
    
    def _optimize_query(self, query: str) -> str:
        """
        优化搜索查询
        
        Args:
            query: 原始查询
            
        Returns:
            str: 优化后的查询
        """
        # 根据查询内容判断是否添加科技新闻或学术论文相关关键词
        if any(term in query.lower() for term in ["科技", "技术", "创新", "研发", "发布", "产品", "技术趋势"]):
            # 为科技新闻查询添加优化关键词
            tech_terms = ["最新", "科技新闻", "技术动态", "创新", "前沿"]
            selected_terms = [term for term in tech_terms if term not in query.lower()]
            
            if selected_terms:
                return query + " " + " ".join(selected_terms[:2])  # 最多添加2个关键词
            
        elif any(term in query.lower() for term in ["论文", "研究", "学术", "方法", "实验", "理论", "发现"]):
            # 为学术论文查询添加优化关键词
            academic_terms = ["论文", "研究", "学术", "site:arxiv.org OR site:nature.com OR site:science.org"]
            selected_terms = [term for term in academic_terms if term not in query.lower()]
            
            if selected_terms:
                return query + " " + " ".join(selected_terms[:2])  # 最多添加2个关键词
        
        # 默认返回原查询
        return query
    
    def _calculate_relevance(self, query: str, content: str) -> float:
        """
        计算内容与查询的相关性得分
        
        Args:
            query: 搜索查询
            content: 内容文本
            
        Returns:
            float: 相关性得分 (0-1)
        """
        # 简单相关性计算：基于关键词匹配
        # 实际应用中可以使用更复杂的算法，如TF-IDF、余弦相似度等
        
        # 将查询分词
        query_terms = re.findall(r'\w+', query.lower())
        
        if not query_terms:
            return 0.0
        
        # 计算内容中包含的查询词数量
        content_lower = content.lower()
        matches = sum(1 for term in query_terms if term in content_lower)
        
        # 计算基础相关性得分
        base_score = matches / len(query_terms)
        
        # 考虑精确匹配的加权
        exact_match_bonus = 0.2 if query.lower() in content_lower else 0.0
        
        # 考虑关键词密度
        content_length = max(1, len(content))
        density_factor = min(1.0, len(''.join(query_terms)) / content_length * 10)
        
        # 最终得分：基础得分 + 精确匹配奖励 + 密度因子（有一定权重）
        final_score = min(1.0, base_score * 0.6 + exact_match_bonus + density_factor * 0.2)
        
        return final_score

    async def search_tech_news(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        专门搜索科技新闻
        
        Args:
            query: 搜索查询
            max_results: 最大结果数量
            
        Returns:
            List[Dict[str, Any]]: 科技新闻搜索结果
        """
        # 优化查询词，添加科技新闻特定的关键词
        optimized_query = f"{query} 最新科技新闻 技术动态 (site:techcrunch.com OR site:wired.com OR site:theverge.com OR site:mit.edu/news OR site:technologyreview.com)"
        
        # 执行搜索
        results = await self.search(optimized_query)
        
        # 过滤和格式化结果
        tech_news = []
        for result in results:
            # 提取日期信息（尝试从标题或摘要中提取）
            date_match = re.search(r'(\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2})|(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{4})', 
                                  result.get("title", "") + " " + result.get("snippet", ""))
            published_date = date_match.group(0) if date_match else ""
            
            # 创建科技新闻条目
            news_item = {
                "title": result.get("title", ""),
                "url": result.get("link", ""),
                "source": self._extract_domain(result.get("link", "")),
                "content": result.get("snippet", ""),
                "published_date": published_date,
                "relevance": result.get("relevance", 0.5),
                "source_type": "tech_news"
            }
            
            tech_news.append(news_item)
        
        # 按相关性排序
        tech_news.sort(key=lambda x: x["relevance"], reverse=True)
        
        # 返回前N条结果
        return tech_news[:max_results]
    
    async def search_academic_papers(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        专门搜索学术论文
        
        Args:
            query: 搜索查询
            max_results: 最大结果数量
            
        Returns:
            List[Dict[str, Any]]: 学术论文搜索结果
        """
        # 优化查询词，添加学术论文特定的关键词和来源
        optimized_query = f"{query} research paper academic (site:arxiv.org OR site:nature.com OR site:science.org OR site:ieee.org OR site:acm.org)"
        
        # 执行搜索
        results = await self.search(optimized_query)
        
        # 过滤和格式化结果
        papers = []
        for result in results:
            # 尝试提取作者信息
            authors = ""
            author_match = re.search(r'by\s+([^\.]+)', result.get("snippet", ""))
            if author_match:
                authors = author_match.group(1).strip()
            
            # 提取日期信息
            date_match = re.search(r'(\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2})|(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{4})', 
                                  result.get("title", "") + " " + result.get("snippet", ""))
            published_date = date_match.group(0) if date_match else ""
            
            # 创建论文条目
            paper_item = {
                "title": result.get("title", ""),
                "url": result.get("link", ""),
                "journal": self._extract_domain(result.get("link", "")),
                "authors": authors,
                "abstract": result.get("snippet", ""),
                "published_date": published_date,
                "relevance": result.get("relevance", 0.5),
                "source_type": "academic_paper"
            }
            
            papers.append(paper_item)
        
        # 按相关性排序
        papers.sort(key=lambda x: x["relevance"], reverse=True)
        
        # 返回前N条结果
        return papers[:max_results]
    
    def _extract_domain(self, url: str) -> str:
        """
        从URL中提取域名作为来源
        
        Args:
            url: 网址
            
        Returns:
            str: 域名（来源）
        """
        try:
            # 提取域名
            domain_match = re.search(r'https?://(?:www\.)?([^/]+)', url)
            if domain_match:
                domain = domain_match.group(1)
                
                # 规范化一些常见的科技新闻和学术网站
                domain_mapping = {
                    "arxiv.org": "arXiv",
                    "nature.com": "Nature",
                    "science.org": "Science",
                    "ieee.org": "IEEE",
                    "acm.org": "ACM Digital Library",
                    "techcrunch.com": "TechCrunch",
                    "wired.com": "Wired",
                    "theverge.com": "The Verge",
                    "technologyreview.com": "MIT Technology Review",
                    "mit.edu": "MIT News"
                }
                
                # 查找完全匹配
                if domain in domain_mapping:
                    return domain_mapping[domain]
                
                # 查找部分匹配
                for key, value in domain_mapping.items():
                    if key in domain:
                        return value
                
                return domain
            
            return "未知来源"
        except Exception as e:
            logger.error(f"提取域名时出错: {e}")
            return "未知来源"
