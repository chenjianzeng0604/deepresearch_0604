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
        self.semaphore = asyncio.Semaphore(int(os.getenv("CRAWLER_MAX_CONCURRENT_TASKS", 3)))
    
    async def _execute_task_with_semaphore(self, task_func, *args, **kwargs):
        """
        使用信号量执行任务，限制并发数量
        
        Args:
            task_func: 要执行的任务函数
            args: 位置参数
            kwargs: 关键字参数
            
        Returns:
            任务执行结果
        """
        async with self.semaphore:
            logger.debug(f"获取信号量，执行任务: {task_func.__name__}")
            try:
                result = await task_func(*args, **kwargs)
                return result
            except Exception as e:
                logger.error(f"任务执行出错: {task_func.__name__}, {str(e)}", exc_info=True)
                raise
            finally:
                logger.debug(f"释放信号量，任务完成: {task_func.__name__}")
    
    async def scheduled_crawl(self, keywords: List[str], scenario: str = None):
        """
        定时执行爬虫任务
        
        Args:
            keywords: 搜索关键词列表
            scenario: 场景名称
        """
        if not keywords or len(keywords) == 0:
            logger.error("搜索关键词列表为空，无法执行爬虫任务")
            return
        if not scenario:
            scenario = self.agent.crawler_manager.config.default_scenario
            
        search_url_formats = self.agent.crawler_manager.config.get_search_url_formats(scenario)
        search_urls = self.agent.crawler_manager.config.get_search_url(scenario)

        if scenario == "healthcare":
            platforms = ["web_site", "arxiv", "search"]
        elif scenario == "ai":
            platforms = ["web_site", "github", "arxiv", "weixin", "search"]
        else:
            platforms = ["web_site", "search"]
            
        start_time = datetime.now()
        logger.info(f"开始执行定时爬虫任务，时间: {start_time}, 关键词：{keywords}，平台：{platforms}, 场景：{scenario}")
        
        all_links = []
        all_tasks = []
        
        for keyword in keywords:
            try:
                logger.info(f"处理关键词: {keyword}, 场景: {scenario}")
                
                if "web_site" in platforms and search_url_formats:
                    for search_engine, search_url_format in search_url_formats.items():
                        try:
                            encoded_query = quote(keyword)
                            search_url = search_url_format.format(encoded_query)
                            logger.info(f"从 {search_engine} 获取 '{keyword}' 相关文章，URL: {search_url}")
                            
                            web_crawler = self.agent.crawler_manager.web_crawler
                            links = await self._execute_task_with_semaphore(web_crawler.parse_sub_url, search_url)
                            if not links:
                                logger.warning(f"无法从 {search_url} 获取文章链接: {keyword}")
                                continue
                                
                            all_links.extend(links)
                            task = asyncio.create_task(self._execute_task_with_semaphore(
                                web_crawler.fetch_article_and_save2milvus, keyword, links, scenario))
                            all_tasks.append(task)
                            logger.info(f"为关键词 '{keyword}' 场景 '{scenario}' 在 {search_engine} 找到 {len(links)} 个链接")
                        except Exception as e:
                            logger.error(f"从 {search_engine} 获取文章时出错: {str(e)}")
                
                if "web_site" in platforms and search_urls:
                    logger.info(f"使用场景 '{scenario}' 的自定义URL爬取关键词 '{keyword}'")
                    task = asyncio.create_task(self._execute_task_with_semaphore(
                        self.agent.crawler_manager.web_crawler.fetch_article_and_save2milvus, keyword, search_urls, scenario))
                    all_tasks.append(task)
                
                if "github" in platforms:
                    try:
                        logger.info(f"从GitHub获取 '{keyword}' 相关仓库")
                        github_crawler = self.agent.crawler_manager.github_crawler
                        links = await self._execute_task_with_semaphore(github_crawler.parse_sub_url, keyword)
                        if links:
                            all_links.extend(links)
                            task = asyncio.create_task(self._execute_task_with_semaphore(
                                github_crawler.fetch_article_and_save2milvus, keyword, links, scenario))
                            all_tasks.append(task)
                        else:
                            logger.warning(f"无法从 GitHub 获取仓库: {keyword}")
                    except Exception as e:
                        logger.error(f"GitHub仓库爬取时出错: {str(e)}")
                
                if "arxiv" in platforms:
                    try:
                        logger.info(f"从arXiv获取 '{keyword}' 相关论文")
                        arxiv_crawler = self.agent.crawler_manager.arxiv_crawler
                        links = await self._execute_task_with_semaphore(arxiv_crawler.parse_sub_url, keyword)
                        if links:
                            all_links.extend(links)
                            task = asyncio.create_task(self._execute_task_with_semaphore(
                                arxiv_crawler.fetch_article_and_save2milvus, keyword, links, scenario))
                            all_tasks.append(task)
                        else:
                            logger.warning(f"无法从 arXiv 获取文章: {keyword}")
                    except Exception as e:
                        logger.error(f"arXiv论文爬取时出错: {str(e)}")
                
                if "weixin" in platforms:
                    try:
                        logger.info(f"从微信获取 '{keyword}' 相关文章")
                        wechat_crawler = self.agent.crawler_manager.wechat_crawler
                        links = await self._execute_task_with_semaphore(wechat_crawler.parse_sub_url, keyword)
                        if links:
                            all_links.extend(links)
                            task = asyncio.create_task(self._execute_task_with_semaphore(
                                wechat_crawler.fetch_article_and_save2milvus, keyword, links, scenario))
                            all_tasks.append(task)
                        else:
                            logger.warning(f"无法从微信获取文章: {keyword}")
                    except Exception as e:
                        logger.error(f"微信文章爬取时出错: {str(e)}")
                
                if "search" in platforms:
                    try:
                        logger.info(f"使用WebSearcher搜索获取 '{keyword}' 相关文章")
                        search_results = await self._execute_task_with_semaphore(self.agent.web_searcher.search, keyword)
                        if search_results:
                            links = []
                            for result in search_results:
                                if "link" in result and result["link"]:
                                    links.append(result["link"])
                            if links:
                                all_links.extend(links)
                                task = asyncio.create_task(self._execute_task_with_semaphore(
                                    self.agent.crawler_manager.web_crawler.fetch_article_and_save2milvus, keyword, links, scenario))
                                all_tasks.append(task)
                                logger.info(f"从WebSearcher获取到 {len(links)} 个有效链接")
                            else:
                                logger.warning(f"搜索结果中没有有效链接: {keyword}")
                        else:
                            logger.warning(f"无法通过WebSearcher获取搜索结果: {keyword}")
                    except Exception as e:
                        logger.error(f"使用WebSearcher搜索获取文章时出错: {str(e)}")
                
            except Exception as e:
                logger.error(f"处理关键词 '{keyword}' 时出错: {str(e)}")
        
        if all_tasks:
            logger.info(f"等待 {len(all_tasks)} 个爬取任务完成...")
            await asyncio.gather(*all_tasks, return_exceptions=True)
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.info(f"爬取任务已完成，共处理 {len(all_links)} 个链接，耗时 {duration:.2f} 秒")
        else:
            logger.warning("没有生成任何爬取任务")
        
    def start_scheduled_crawl(self, keywords: List[str], scenario: str = None):
        """
        启动定时爬虫任务，不同场景在不同时间执行
        
        Args:
            keywords: 搜索关键词列表
            scenario: 指定的场景，如 "ai" 或 "healthcare"，为None时使用全部场景
        """
        if not self.scheduler.running:
            # 为特定场景添加定时任务
            if scenario not in self.agent.crawler_manager.config.supported_scenarios:
                logger.warning(f"不支持的场景: {scenario}，使用默认场景")
                scenario = self.agent.crawler_manager.config.default_scenario
            
            # 根据场景选择时间
            hour = 0
            if scenario == "general":
                hour = 0  # 通用场景早上0点
            elif scenario == "healthcare":
                hour = 1  # 医疗健康场景早上1点
            elif scenario == "ai":
                hour = 4  # AI场景早上4点
            
            self.scheduler.add_job(
                self.scheduled_crawl,
                CronTrigger(hour=hour, minute=0),
                args=[keywords, scenario],
                id=f'crawl_task_{scenario}',
                replace_existing=True
            )
            
            logger.info(f"已为场景 '{scenario}' 添加定时任务，执行时间: 每天{hour}:00")
            
            # 启动调度器
            self.scheduler.start()
            self.running = True
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
            self.scheduler.remove_job('crawl_task_ai')
            self.scheduler.remove_job('crawl_task_healthcare')
            self.scheduler.shutdown()
            self.running = False
            logger.info("已停止定时爬虫任务")
            return True
        else:
            logger.info("调度器未在运行")
            return False
            
    async def run_crawl_now(self, keywords: List[str], scenario: str = None):
        """
        立即执行一次爬虫任务
        
        Args:
            keywords: 搜索关键词列表
            scenario: 场景名称
        """
        logger.info(f"立即执行爬虫任务，关键词：{keywords}，场景：{scenario}")
        await self.scheduled_crawl(keywords, scenario)

# 全局实例，用于命令行调用
scheduler_instance = None

async def start_scheduler(keywords: List[str], scenario: str = None, run_now: bool = False):
    """
    启动定时任务调度器
    
    Args:
        keywords: 搜索关键词列表
        scenario: 场景名称
        all_scenarios: 是否启动所有支持的场景
        run_now: 是否立即执行一次
    """
    global scheduler_instance
    
    if scheduler_instance is None:
        scheduler_instance = ScheduledCrawler()
    
    # 启动定时任务
    scheduler_instance.start_scheduled_crawl(keywords, scenario)
    
    # 如果需要，立即执行一次
    if run_now:
        logger.info("立即执行一次爬虫任务")
        await scheduler_instance.run_crawl_now(keywords, scenario)
    
    return scheduler_instance

async def stop_scheduler():
    """停止调度器"""
    global scheduler_instance
    
    if scheduler_instance:
        result = scheduler_instance.stop_scheduled_crawl()
        return result
    return False
