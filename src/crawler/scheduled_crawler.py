#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
定时爬虫任务模块 - 提供每天凌晨2点和下午2点自动执行爬虫任务的功能
"""

import os
import asyncio
import logging
import sys
import time
from typing import List, Dict, Any
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import signal

from src.agents.deepresearch_agent import DeepresearchAgent
from urllib.parse import quote

logger = logging.getLogger(__name__)

class ScheduledCrawler:
    """
    定时爬虫任务管理器，提供定时执行爬虫任务的功能
    """
    
    def __init__(self):
        """
        初始化定时爬虫任务管理器
        """
        self.agent = DeepresearchAgent()
        self.scheduler = AsyncIOScheduler()
        self.running = False
    
    async def crawl_content(self, query: str, platforms: List[str]) -> tuple:
        """
        爬取内容的核心方法
        
        Args:
            query: 搜索查询
            platforms: 搜索平台列表
            
        Returns:
            Tuple[List[str], List[asyncio.Task]]: 所有链接和异步任务
        """
        all_links = []
        tasks = []
            
        logger.info(f"正在获取爬虫内容: {query}")
        try:
            if "web_site" in platforms:
                web_crawler = self.agent.crawler_manager.web_crawler
                for search_url_format in self.agent.crawler_manager.config.search_url_formats.values():
                    search_url = search_url_format.format(quote(query))
                    links = await web_crawler.parse_sub_url(search_url)
                    if not links:
                        logger.warning(f"无法从 {search_url} 获取文章: {query}")
                        continue
                    all_links.extend(links)
                    tasks.append(web_crawler.fetch_article_and_save2milvus(query, links))

            if "web_site" in platforms and self.agent.crawler_manager.config.search_url and len(self.agent.crawler_manager.config.search_url) > 0:
                tasks.append(web_crawler.fetch_article_and_save2milvus(query, self.agent.crawler_manager.config.search_url))
            
            if "github" in platforms:
                github_crawler = self.agent.crawler_manager.github_crawler
                links = await github_crawler.parse_sub_url(query)
                if not links:
                    logger.warning(f"无法从 GitHub 获取仓库: {query}")
                else:
                    all_links.extend(links)
                    tasks.append(github_crawler.fetch_article_and_save2milvus(query, links))

            if "arxiv" in platforms:
                arxiv_crawler = self.agent.crawler_manager.arxiv_crawler
                links = await arxiv_crawler.parse_sub_url(query)
                if not links:
                    logger.warning(f"无法从 arXiv 获取文章: {query}")
                else:
                    all_links.extend(links)
                    tasks.append(arxiv_crawler.fetch_article_and_save2milvus(query, links))

            if "weixin" in platforms:
                wechat_crawler = self.agent.crawler_manager.wechat_crawler
                links = await wechat_crawler.parse_sub_url(query)
                if not links:
                    logger.warning(f"无法从微信获取文章: {query}")
                else:
                    all_links.extend(links)
                    tasks.append(wechat_crawler.fetch_article_and_save2milvus(query, links))

            if "search" in platforms:
                try:
                    logger.info(f"使用WebSearcher搜索获取文章: {query}")
                    search_results = await self.agent.web_searcher.search(query)
                    if not search_results:
                        logger.warning(f"无法通过WebSearcher获取搜索结果: {query}")
                    else:
                        links = []
                        for result in search_results:
                            if "link" in result and result["link"]:
                                links.append(result["link"])
                        if links:
                            all_links.extend(links)
                            tasks.append(self.agent.crawler_manager.web_crawler.fetch_article_and_save2milvus(query, links))
                        else:
                            logger.warning(f"搜索结果中没有有效链接: {query}")
                except Exception as e:
                    logger.error(f"使用WebSearcher搜索获取文章时出错: {query}, {str(e)}", exc_info=True)
        except Exception as e:
            logger.error(f"获取爬虫内容时出错: {query}, {str(e)}", exc_info=True)
            
        return all_links, tasks
    
    async def scheduled_crawl(self, keywords: List[str], platforms: List[str]):
        """
        定时执行爬虫任务
        
        Args:
            keywords: 搜索关键词列表
            platforms: 搜索平台列表
        """
        logger.info(f"开始执行定时爬虫任务，关键词：{keywords}，平台：{platforms}")
        all_links = []
        all_tasks = []
        
        for query in keywords:
            links, tasks = await self.crawl_content(query, platforms)
            all_links.extend(links)
            all_tasks.extend(tasks)
        
        try:
            if all_tasks:
                results = await asyncio.gather(*all_tasks, return_exceptions=True)
                logger.info(f"定时爬虫任务完成，处理了 {len(all_tasks)} 个任务，获取了 {len(all_links)} 个链接")
                
                # 检查异常
                exceptions = [r for r in results if isinstance(r, Exception)]
                if exceptions:
                    logger.warning(f"定时爬虫任务中有 {len(exceptions)} 个任务发生异常")
            else:
                logger.warning("定时爬虫任务未生成任何处理任务")
        except Exception as e:
            logger.error(f"执行定时爬虫任务时出错: {str(e)}", exc_info=True)
            
    def start_scheduled_crawl(self, keywords: List[str], platforms: List[str]):
        """
        启动定时爬虫任务，每天凌晨2点和下午2点各执行一次
        
        Args:
            keywords: 搜索关键词列表
            platforms: 搜索平台列表
        """
        if not self.scheduler.running:
            # 添加定时任务，每天凌晨2点执行
            self.scheduler.add_job(
                self.scheduled_crawl,
                CronTrigger(hour=2, minute=0),
                args=[keywords, platforms],
                id='crawl_task_morning',
                replace_existing=True
            )
            
            # 添加定时任务，每天下午2点执行
            self.scheduler.add_job(
                self.scheduled_crawl,
                CronTrigger(hour=14, minute=0),
                args=[keywords, platforms],
                id='crawl_task_afternoon',
                replace_existing=True
            )
            
            # 启动调度器
            self.scheduler.start()
            self.running = True
            logger.info(f"已启动定时爬虫任务，关键词：{keywords}，平台：{platforms}")
            return True
        else:
            logger.info("调度器已在运行中")
            return False
            
    def stop_scheduled_crawl(self):
        """
        停止定时爬虫任务
        
        Returns:
            bool: 是否成功停止
        """
        if self.scheduler.running:
            self.scheduler.remove_job('crawl_task_morning')
            self.scheduler.remove_job('crawl_task_afternoon')
            self.scheduler.shutdown()
            self.running = False
            logger.info("已停止定时爬虫任务")
            return True
        else:
            logger.info("调度器未在运行")
            return False
            
    async def run_crawl_now(self, keywords: List[str], platforms: List[str]):
        """
        立即执行一次爬虫任务
        
        Args:
            keywords: 搜索关键词列表
            platforms: 搜索平台列表
        """
        logger.info(f"立即执行爬虫任务，关键词：{keywords}，平台：{platforms}")
        await self.scheduled_crawl(keywords, platforms)

# 全局实例，用于命令行调用
scheduler_instance = None

async def start_scheduler(keywords: List[str], platforms: List[str], run_now: bool = False):
    """
    启动定时任务调度器
    
    Args:
        keywords: 搜索关键词列表
        platforms: 搜索平台列表
        run_now: 是否立即执行一次
    """
    global scheduler_instance
    
    if scheduler_instance is None:
        scheduler_instance = ScheduledCrawler()
    
    # 启动定时任务（2点和14点）
    scheduler_instance.start_scheduled_crawl(keywords, platforms)
    
    # 如果需要，立即执行一次
    if run_now:
        logger.info("立即执行一次爬虫任务")
        await scheduler_instance.run_crawl_now(keywords, platforms)
    
    return scheduler_instance

async def stop_scheduler():
    """停止调度器"""
    global scheduler_instance
    
    if scheduler_instance:
        result = scheduler_instance.stop_scheduled_crawl()
        return result
    return False
