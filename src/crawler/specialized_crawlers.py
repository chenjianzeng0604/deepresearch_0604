"""
专用爬虫模块，针对特定网站提供优化的爬取功能
"""
import asyncio
import logging
import re
import os
import json
from typing import Dict, List, Any, Optional, Set
from urllib.parse import urlparse, urljoin, quote
import aiohttp
import requests

from bs4 import BeautifulSoup

from src.crawler.web_crawlers import WebCrawler

logger = logging.getLogger(__name__)

class ArxivCrawler(WebCrawler):
    """
    专用于Arxiv论文网站的爬虫
    """
    
    def __init__(self):
        """初始化Arxiv爬虫"""
        super().__init__()
    
    def is_valid_url(self, url: str) -> bool:
        """
        检查URL是否有效且符合arxiv爬取要求
        
        Args:
            url: 要检查的URL
        
        Returns:
            bool: 如果URL有效且应该被爬取则返回True
        """
        # 检查基本有效性
        if not url or not isinstance(url, str):
            return False
        
        # 确保URL是arxiv相关
        if not ('arxiv.org' in url):
            return False
        
        # 专注于论文页面，排除其他arxiv页面如博客、帮助等
        if any(exclude in url for exclude in ['/blog/', '/help/', '/about/', '/login/', '/search/']):
            return False
        
        # 如果URL包含具体论文标识（通常是abs/或html/或pdf/开头的路径）则认为有效
        return '/abs/' in url or '/html/' in url or '/pdf/' in url
    
    def is_arxiv_url(self, url: str) -> bool:
        """
        检查URL是否为ArXiv的URL
        
        Args:
            url: 要检查的URL
            
        Returns:
            bool: 如果是ArXiv URL则返回True
        """
        if not url or not isinstance(url, str):
            return False
            
        return 'arxiv.org' in url or '/arxiv/' in url

    async def parse_sub_url(self, query: str) -> List[str]:
        """
        搜索ArXiv论文
        
        Args:
            query: 搜索关键词
        Returns:
            List[str]: 搜索结果列表
        """
        # 对非英文查询进行处理，增加相关英文关键词，提高搜索质量
        enhanced_query = query
        
        # 如果查询包含中文字符，添加英文关键词增强查询
        if any(u'\u4e00' <= c <= u'\u9fff' for c in query):
            # 将常见的中文医疗AI术语映射到英文
            cn_to_en_terms = {
                "人工智能": "artificial intelligence",
                "医疗": "healthcare medical",
                "诊断": "diagnosis diagnostic",
                "影像": "imaging radiology",
                "机器学习": "machine learning",
                "深度学习": "deep learning",
                "预测": "prediction predictive",
                "预防": "prevention preventive",
                "治疗": "treatment therapy",
                "患者": "patient"
            }
            
            # 尝试添加英文关键词
            english_terms = []
            for cn_term, en_term in cn_to_en_terms.items():
                if cn_term in query:
                    english_terms.append(en_term)
            
            # 构建增强的英文查询
            if english_terms:
                enhanced_query = " ".join(english_terms)
                logger.info(f"将中文查询 '{query}' 增强为英文查询 '{enhanced_query}'")
        
        # 对查询进行URL编码
        encoded_query = quote(enhanced_query)
        search_url = f"https://arxiv.org/search/?query={encoded_query}&searchtype=all"
        
        try:
            logger.info(f"搜索ArXiv论文: {search_url}")
            response = await self.fetch_url(search_url)
            
            if not response:
                logger.error(f"获取ArXiv搜索结果失败: {search_url}")
                return []
                
            soup = BeautifulSoup(response, 'html.parser')
            paper_links = []
            paper_ids = []

            # 首先尝试新版arXiv页面格式提取论文ID或链接
            for a_tag in soup.select('a'):
                # 尝试找到论文链接
                if a_tag and 'href' in a_tag.attrs:
                    link = a_tag['href']
                    if 'arxiv.org' not in link:
                        link = 'https://arxiv.org' + link
                    if not self.is_valid_url(link):
                        continue
                    paper_links.append(link)
                    
                    # 同时提取论文ID
                    paper_id_match = re.search(r'(\d+\.\d+)', link)
                    if paper_id_match:
                        paper_ids.append(paper_id_match.group(1))
            
            # 如果只有ID没有完整链接，构建链接
            if len(paper_ids) > len(paper_links):
                paper_links = [f"https://arxiv.org/abs/{paper_id}" for paper_id in paper_ids]
            return paper_links
        except Exception as e:
            logger.error(f"搜索ArXiv论文时出错: {e}", exc_info=True)
            return []

    async def fetch_url(self, url: str) -> Optional[str]:
        """
        获取URL内容，带重试机制
        
        Args:
            url: 目标URL
            max_retries: 最大重试次数
            retry_delay: 重试延迟(秒)
            
        Returns:
            Optional[str]: HTML内容
        """
        for attempt in range(1, self.crawler_fetch_url_max_retries + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.headers, timeout=self.crawler_fetch_url_timeout) as response:
                        if response.status == 200:
                            return await response.text()
                        elif response.status == 429:  # 被限流
                            logger.warning(f"请求被限流 (HTTP 429)，等待重试: {url}")
                        else:
                            logger.error(f"HTTP错误 {response.status}: {url}")
                            
                # 只有非成功响应才会执行到这里
                if attempt < self.crawler_fetch_url_max_retries:
                    wait_time = self.crawler_fetch_url_retry_delay * attempt
                    logger.info(f"等待 {wait_time} 秒后进行第 {attempt+1}/{self.crawler_fetch_url_max_retries} 次重试...")
                    await asyncio.sleep(wait_time)
                    
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"获取URL出错 (尝试 {attempt}/{self.crawler_fetch_url_max_retries}): {url}, 错误: {str(e)}")
                if attempt < self.crawler_fetch_url_max_retries:
                    wait_time = self.crawler_fetch_url_retry_delay * attempt
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    await asyncio.sleep(wait_time)
            except Exception as e:
                logger.exception(f"获取URL时发生意外错误: {url}")
                if attempt < self.crawler_fetch_url_max_retries:
                    wait_time = self.crawler_fetch_url_retry_delay * attempt
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    await asyncio.sleep(wait_time)
        
        logger.error(f"在{self.crawler_fetch_url_max_retries}次尝试后仍无法获取URL: {url}")
        return None

class GithubCrawler(WebCrawler):
    """
    专用于GitHub的爬虫
    """
    
    def __init__(self):
        """初始化GitHub爬虫"""
        super().__init__()
        self.github_token = os.getenv("GITHUB_TOKEN")
    
    def is_github_url(self, url: str) -> bool:
        """
        检查URL是否为GitHub的URL
        
        Args:
            url: 要检查的URL
            
        Returns:
            bool: 如果是GitHub URL则返回True
        """
        if not url or not isinstance(url, str):
            return False
            
        return 'github.com' in url or '/github/' in url
            
    async def parse_sub_url(self, query: str) -> List[str]:
        """
        在GitHub上搜索仓库
        
        Args:
            query: 搜索关键词
        Returns:
            List[str]: 搜索结果列表
        """
        repo_urls = await self.fetch_repos_by_github_search_api(query)
        if not repo_urls:
            repo_urls = await self.fetch_repos_by_github_search_url(query)
        return repo_urls

    async def fetch_repos_by_github_search_api(self, keyword):
        url = "https://api.github.com/search/repositories"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Python-Script",
            "Authorization": f"token {self.github_token}"
        }
        params = {
            "q": keyword,
            "sort": "stars",
            "order": "desc",
            "per_page": 1000
        }
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            urls = []
            for repo in data["items"]:
                urls.append(repo['html_url'])
            return urls
        except Exception as e:
            print(f"请求失败: {e}")
        return []

    async def fetch_repos_by_github_search_url(self, keyword):
        encoded_query = quote(keyword)
        search_url = f"https://github.com/search?q={encoded_query}&type=repositories"
        try:       
            html_content = await super().fetch_url(search_url)
            if not html_content:
                logger.warning(f"GitHub搜索请求失败:{search_url}")
                return []
            
            soup = BeautifulSoup(html_content, 'html.parser')
            repo_urls = []
            repo_items = []

            try:
                repo_items = soup.select('div[data-testid="results-list"] div')
                if repo_items:
                    logger.info(f"使用results-list选择器找到 {len(repo_items)} 个项目")
            except Exception as e:
                logger.error(f"results-list选择器错误: {str(e)}", exc_info=True)
                
            if not repo_items:
                logger.warning(f"无法从GitHub页面解析仓库列表:{search_url}")
                return []
                
            for idx, item in enumerate(repo_items):  
                try:
                    repo_link = None
                    for selector in ['h3 a']:
                        try:
                            repo_link = item.select_one(selector)
                            if repo_link:
                                break
                        except Exception:
                            continue
                    
                    if not repo_link:
                        continue
                        
                    repo_url = urljoin("https://github.com", repo_link.get('href', ''))
                    repo_urls.append(repo_url)
                except Exception as e:
                    logger.warning(f"解析GitHub仓库信息时出错 (项目 {idx}): {str(e)}")
                    continue
            
            if repo_urls:
                return repo_urls[:1000]
                
        except Exception as e:
            logger.warning(f"GitHub搜索错误 ({search_url}): {str(e)}")

        return []

class WeChatOfficialAccountCrawler(WebCrawler):
    """
    专用于微信公众号文章的爬虫
    """
    
    def __init__(self):
        """初始化微信公众号爬虫"""
        super().__init__()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        # 微信文章选择器
        self.selectors = {
            'title': '#activity-name',
            'author': '#js_name',
            'date': '#publish_time',
            'content': '#js_content',
        }
            
    async def parse_sub_url(self, query: str) -> List[str]:
        """
        搜索微信公众号文章
        
        Args:
            query: 搜索查询
        Returns:
            List[str]: 文章URL列表
        """
        logger.info(f"搜索微信公众号文章: {query}")
        
        # 搜狗微信搜索URL
        search_url = f"https://weixin.sogou.com/weixin?type=2&query={quote(query)}"
        
        try:
            html_content = await self.fetch_url(search_url)
            if not html_content:
                logger.error(f"无法获取微信搜索结果: {search_url}")
                return []
                
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 提取搜索结果
            results = []
            articles = soup.select('.news-box .news-list li')
            
            for article in articles:
                try:
                    link_elem = article.select_one('h3 a')
                    
                    if link_elem:
                        url = link_elem.get('href', '')
                        # 对URL进行完整处理
                        if url and not url.startswith('http'):
                            url = urljoin('https://weixin.sogou.com/', url)
                            
                        results.append(url)
                except Exception as e:
                    logger.error(f"处理微信搜索结果项时出错: {str(e)}", exc_info=True)
                    continue
                    
            return results
            
        except Exception as e:
            logger.error(f"搜索微信公众号文章出错: {query}, 错误: {str(e)}", exc_info=True)
            return []