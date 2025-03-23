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
        
        if self.search_engine == "bing":
            return await self._search_bing(query)
        elif self.search_engine == "google":
            return await self._search_google(query)
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
            logger.info(f"使用Google Search API搜索: {query}")

            base_url = "https://google.serper.dev/search"
            headers = {
                'X-API-KEY': self.api_key,
                'Content-Type': 'application/json'
            }
            payload = json.dumps({
                'q': query
            })
            
            max_retries = 2
            data = None  # 初始化data变量，避免未赋值就引用的错误
            for attempt in range(max_retries):
                try:
                    timeout = aiohttp.ClientTimeout(total=10)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.post(base_url, headers=headers, data=payload) as response:
                            if response.status == 200:
                                data = await response.json()
                                break
                            else:
                                logger.error(f"Google API响应错误: {response.status}")
                                if attempt == max_retries - 1:
                                    break
                                await asyncio.sleep(1)
                except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
                    logger.error(f"连接Google API时发生错误 (尝试 {attempt+1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"调用Google API时发生未知错误: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
            
            results = []
            if data and 'organic' in data:  # 检查data是否已被赋值且包含'organic'键
                for item in data['organic']:
                    result = {
                        'title': item.get('title', ''),
                        'link': item.get('link', ''),
                        'source': 'Google Search'
                    }
                    results.append(result)
            
            logger.info(f"成功获取Google搜索结果: {len(results)} 条")
            return results
        except Exception as e:
            logger.error(f"Google搜索过程中发生错误: {e}")
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
            
            endpoint = "https://api.bing.microsoft.com/v7.0/search"
            
            headers = {
                "Ocp-Apim-Subscription-Key": self.api_key
            }
            
            params = {
                "q": query,
                "count": min(50, self.config.max_results),
                "offset": 0,
                "mkt": "zh-CN",
                "freshness": "Month"
            }

            max_retries = 2
            for attempt in range(max_retries):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(endpoint, headers=headers, params=params) as response:
                            if response.status == 200:
                                data = await response.json()
                                break
                            else:
                                logger.error(f"Bing API响应错误: {response.status}")
                                if attempt == max_retries - 1:
                                    break
                                await asyncio.sleep(1)
                except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
                    logger.error(f"连接Bing API时发生错误 (尝试 {attempt+1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"调用Bing API时发生未知错误: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
            
            results = []
            if "webPages" in data and "value" in data["webPages"]:
                web_pages = data["webPages"]["value"]
                for page in web_pages:
                    results.append({
                        "title": page.get("name", ""),
                        "link": page.get("url", ""),
                        "source": "Bing"
                    })

            return results
        except Exception as e:
            logger.error(f"Bing搜索出错: {e}", exc_info=True)
            return []
