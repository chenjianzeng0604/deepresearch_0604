"""
专用爬虫模块，针对特定网站提供优化的爬取功能
"""
import asyncio
import logging
import re
import json
from typing import Dict, List, Any, Optional, Set
from urllib.parse import urlparse, urljoin, quote
import aiohttp

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
        for attempt in range(1, max_retries + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.headers, timeout=timeout) as response:
                        if response.status == 200:
                            return await response.text()
                        elif response.status == 429:  # 被限流
                            logger.warning(f"请求被限流 (HTTP 429)，等待重试: {url}")
                        else:
                            logger.error(f"HTTP错误 {response.status}: {url}")
                            
                # 只有非成功响应才会执行到这里
                if attempt < max_retries:
                    wait_time = retry_delay * attempt
                    logger.info(f"等待 {wait_time} 秒后进行第 {attempt+1}/{max_retries} 次重试...")
                    await asyncio.sleep(wait_time)
                    
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"获取URL出错 (尝试 {attempt}/{max_retries}): {url}, 错误: {str(e)}")
                if attempt < max_retries:
                    wait_time = retry_delay * attempt
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    await asyncio.sleep(wait_time)
            except Exception as e:
                logger.exception(f"获取URL时发生意外错误: {url}")
                if attempt < max_retries:
                    wait_time = retry_delay * attempt
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    await asyncio.sleep(wait_time)
        
        logger.error(f"在{max_retries}次尝试后仍无法获取URL: {url}")
        return None

class GithubCrawler(WebCrawler):
    """
    专用于GitHub的爬虫
    """
    
    def __init__(self):
        """初始化GitHub爬虫"""
        super().__init__()
    
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
        # 对查询进行URL编码
        encoded_query = quote(query)
        
        # 尝试两种不同的搜索URL
        urls_to_try = [
            f"https://github.com/search?q={encoded_query}&type=repositories",
            f"https://api.github.com/search/repositories?q={encoded_query}&sort=stars&order=desc"
        ]
        
        for search_url in urls_to_try:
            try:
                html_content = await self.fetch_url(search_url)
                if not html_content:
                    logger.warning(f"GitHub搜索请求失败: {search_url}, 尝试下一个URL")
                    continue
                    
                try:        
                    soup = BeautifulSoup(html_content, 'html.parser')
                    repo_urls = []
                    repo_items = []
                    try:
                        repo_items = soup.find_all('li', class_='repo-list-item')
                        if repo_items:
                            logger.info(f"使用repo-list-item选择器找到 {len(repo_items)} 个项目")
                    except Exception as e:
                        logger.error(f"repo-list-item选择器错误: {str(e)}", exc_info=True)
                    
                    if not repo_items:
                        try:
                            repo_items = soup.select('div.Box-row')
                            if repo_items:
                                logger.info(f"使用Box-row选择器找到 {len(repo_items)} 个项目")
                        except Exception as e:
                            logger.error(f"Box-row选择器错误: {str(e)}", exc_info=True)
                    
                    if not repo_items:
                        try:
                            repo_items = soup.select('div[data-testid="results-list"] div')
                            if repo_items:
                                logger.info(f"使用results-list选择器找到 {len(repo_items)} 个项目")
                        except Exception as e:
                            logger.error(f"results-list选择器错误: {str(e)}", exc_info=True)
                    
                    if not repo_items:
                        logger.warning(f"无法从GitHub页面解析仓库列表: {search_url}")
                        continue
                        
                    count = 0
                    for idx, item in enumerate(repo_items):  
                        try:
                            repo_link = None
                            for selector in ['a.v-align-middle', 'a[data-hydro-click*="repository_click"]', 'h3 a']:
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
                            count += 1
                            
                        except Exception as e:
                            logger.error(f"解析GitHub仓库信息时出错 (项目 {idx}): {str(e)}", exc_info=True)
                            continue
                    
                    if repo_urls:
                        return repo_urls
                        
                except Exception as e:
                    logger.error(f"解析GitHub HTML内容时出错: {str(e)}", exc_info=True)
                    continue
                    
            except Exception as e:
                logger.error(f"GitHub搜索错误 ({search_url}): {str(e)}", exc_info=True)
                continue
                
        logger.warning(f"无法从GitHub获取仓库: {encoded_query}")
        return []