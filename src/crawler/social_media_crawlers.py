"""
社交媒体平台爬虫模块，专门用于爬取微信公众号、微博、Twitter、Bilibili等
"""

import logging
import re
import json
import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
from urllib.parse import urlparse, urljoin, quote

import aiohttp
from bs4 import BeautifulSoup
import time
import random

from src.crawler.web_crawlers import WebCrawler

logger = logging.getLogger(__name__)

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


class WeiboCrawler(WebCrawler):
    """
    专用于微博内容的爬虫
    """
    
    def __init__(self):
        """初始化微博爬虫"""
        super().__init__()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        self.search_url = "https://s.weibo.com/weibo/"
            
    async def parse_sub_url(self, query: str) -> List[str]:
        """
        搜索微博帖子
        
        Args:
            query: 搜索查询
        Returns:
            List[str]: 帖子URL列表
        """
        logger.info(f"搜索微博帖子: {query}")
        
        search_url = f"{self.search_url}{quote(query)}"
        
        try:
            html_content = await self.fetch_url(search_url)
            if not html_content:
                logger.error(f"无法获取微博搜索结果: {search_url}")
                return []
                
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 提取搜索结果
            results = []
            posts = soup.select('.card-wrap')
            
            for post in posts:
                try:
                    link_elem = post.select_one('.from a')
                    
                    if link_elem and link_elem.get('href'):
                        url = link_elem.get('href')
                        if not url.startswith('http'):
                            url = 'https://weibo.com' + url
                        
                        results.append(url)
                except Exception as e:
                    logger.error(f"处理微博搜索结果项时出错: {str(e)}", exc_info=True)
                    continue
                    
            return results
            
        except Exception as e:
            logger.error(f"搜索微博帖子出错: {query}, 错误: {str(e)}", exc_info=True)
            return []


class TwitterCrawler(WebCrawler):
    """
    专用于Twitter(X)内容的爬虫
    """
    
    def __init__(self):
        """初始化Twitter爬虫"""
        super().__init__()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        self.base_url = "https://x.com"
        
    async def parse_sub_url(self, query: str) -> List[str]:
        """
        搜索Tweets
        
        Args:
            query: 搜索查询
        Returns:
            List[str]: Tweet URL列表
        """
        logger.info(f"搜索Tweets: {query}")
        
        # 使用Nitter搜索
        search_url = f"https://nitter.net/search?f=tweets&q={quote(query)}"
        
        try:
            html_content = await self.fetch_url(search_url)
            if not html_content:
                logger.error(f"无法获取Twitter搜索结果: {search_url}")
                return []
                
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 提取搜索结果
            results = []
            tweets = soup.select('.timeline-item')
            
            for tweet in tweets[:max_results]:
                try:
                    username_elem = tweet.select_one('.username')
                    date_elem = tweet.select_one('.tweet-date a')
                    
                    if username_elem and date_elem:
                        username = username_elem.text.strip() if username_elem else ""
                        
                        # 构建原始Twitter URL
                        url = ""
                        if username and date_elem and date_elem.get('href'):
                            tweet_path = date_elem.get('href')
                            url = f"https://twitter.com{tweet_path}"
                        
                        results.append(url)
                except Exception as e:
                    logger.error(f"处理Twitter搜索结果项时出错: {str(e)}", exc_info=True)
                    continue
                    
            return results
            
        except Exception as e:
            logger.error(f"搜索Tweets出错: {query}, 错误: {str(e)}", exc_info=True)
            return []