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
        
        # 验证输入参数
        if not query or len(query.strip()) == 0:
            logger.error("搜索查询为空")
            return all_links, tasks
        
        if not platforms or len(platforms) == 0:
            logger.error("平台列表为空")
            return all_links, tasks
        
        # 确保平台列表包含有效值
        valid_platforms = ["web_site", "github", "arxiv", "weixin", "search"]
        platforms = [p for p in platforms if p in valid_platforms]
        
        if not platforms:
            logger.error("没有有效的平台")
            return all_links, tasks
        
        try:
            # Web站点爬取
            if "web_site" in platforms:
                try:
                    web_crawler = self.agent.crawler_manager.web_crawler
                    
                    # 检查配置中的搜索URL格式是否可用
                    if hasattr(self.agent.crawler_manager.config, 'search_url_formats') and self.agent.crawler_manager.config.search_url_formats:
                        for search_engine, search_url_format in self.agent.crawler_manager.config.search_url_formats.items():
                            try:
                                encoded_query = quote(query)
                                search_url = search_url_format.format(encoded_query)
                                logger.info(f"从 {search_engine} 获取 '{query}' 相关文章，URL: {search_url}")
                                
                                links = await web_crawler.parse_sub_url(search_url)
                                if not links:
                                    logger.warning(f"无法从 {search_url} 获取文章: {query}")
                                    continue
                                all_links.extend(links)
                                tasks.append(web_crawler.fetch_article_and_save2milvus(query, links))
                            except Exception as e:
                                logger.error(f"从 {search_engine} 获取文章时出错: {query}, {str(e)}", exc_info=True)
                    else:
                        logger.warning("配置中没有有效的搜索URL格式")
                    
                    # 处理自定义搜索URL
                    if hasattr(self.agent.crawler_manager.config, 'search_url') and self.agent.crawler_manager.config.search_url and len(self.agent.crawler_manager.config.search_url) > 0:
                        logger.info(f"使用自定义搜索URL获取 '{query}' 相关文章")
                        tasks.append(web_crawler.fetch_article_and_save2milvus(query, self.agent.crawler_manager.config.search_url))
                except Exception as e:
                    logger.error(f"Web站点爬取时出错: {query}, {str(e)}", exc_info=True)
            
            # GitHub仓库爬取
            if "github" in platforms:
                try:
                    github_crawler = self.agent.crawler_manager.github_crawler
                    logger.info(f"从GitHub获取 '{query}' 相关仓库")
                    links = await github_crawler.parse_sub_url(query)
                    if not links:
                        logger.warning(f"无法从 GitHub 获取仓库: {query}")
                    else:
                        all_links.extend(links)
                        tasks.append(github_crawler.fetch_article_and_save2milvus(query, links))
                except Exception as e:
                    logger.error(f"GitHub仓库爬取时出错: {query}, {str(e)}", exc_info=True)

            # arXiv论文爬取
            if "arxiv" in platforms:
                try:
                    arxiv_crawler = self.agent.crawler_manager.arxiv_crawler
                    logger.info(f"从arXiv获取 '{query}' 相关论文")
                    links = await arxiv_crawler.parse_sub_url(query)
                    if not links:
                        logger.warning(f"无法从 arXiv 获取文章: {query}")
                    else:
                        all_links.extend(links)
                        tasks.append(arxiv_crawler.fetch_article_and_save2milvus(query, links))
                except Exception as e:
                    logger.error(f"arXiv论文爬取时出错: {query}, {str(e)}", exc_info=True)

            # 微信文章爬取
            if "weixin" in platforms:
                try:
                    wechat_crawler = self.agent.crawler_manager.wechat_crawler
                    logger.info(f"从微信获取 '{query}' 相关文章")
                    links = await wechat_crawler.parse_sub_url(query)
                    if not links:
                        logger.warning(f"无法从微信获取文章: {query}")
                    else:
                        all_links.extend(links)
                        tasks.append(wechat_crawler.fetch_article_and_save2milvus(query, links))
                except Exception as e:
                    logger.error(f"微信文章爬取时出错: {query}, {str(e)}", exc_info=True)

            # Web搜索获取
            if "search" in platforms:
                try:
                    logger.info(f"使用WebSearcher搜索获取 '{query}' 相关文章")
                    search_results = await self.agent.web_searcher.search(query)
                    if not search_results:
                        logger.warning(f"无法通过WebSearcher获取搜索结果: {query}")
                    else:
                        links = []
                        for result in search_results:
                            if "link" in result and result["link"]:
                                links.append(result["link"])
                        if links:
                            logger.info(f"从WebSearcher获取到 {len(links)} 个有效链接")
                            all_links.extend(links)
                            tasks.append(self.agent.crawler_manager.web_crawler.fetch_article_and_save2milvus(query, links))
                        else:
                            logger.warning(f"搜索结果中没有有效链接: {query}")
                except Exception as e:
                    logger.error(f"使用WebSearcher搜索获取文章时出错: {query}, {str(e)}", exc_info=True)
        except Exception as e:
            logger.error(f"获取爬虫内容时出错: {query}, {str(e)}", exc_info=True)
        
        # 为空结果记录日志
        if not all_links:
            logger.warning(f"未能获取到任何链接: {query}")
        if not tasks:
            logger.warning(f"未能生成任何处理任务: {query}")
            
        return all_links, tasks
    
    async def scheduled_crawl(self, keywords: List[str], platforms: List[str]):
        """
        定时执行爬虫任务
        
        Args:
            keywords: 搜索关键词列表
            platforms: 搜索平台列表
        """
        if not keywords or len(keywords) == 0:
            logger.error("搜索关键词列表为空，无法执行爬虫任务")
            return
            
        if not platforms or len(platforms) == 0:
            logger.warning("平台列表为空，将使用所有平台")
            platforms = ["web_site", "github", "arxiv", "weixin", "search"]
            
        start_time = datetime.now()
        logger.info(f"开始执行定时爬虫任务，时间: {start_time}, 关键词：{keywords}，平台：{platforms}")
        
        all_links = []
        all_tasks = []
        failed_keywords = []
        
        # 依次处理每个关键词，避免因一个关键词失败影响整体任务
        for query in keywords:
            try:
                logger.info(f"处理关键词: {query}")
                links, tasks = await self.crawl_content(query, platforms)
                all_links.extend(links)
                all_tasks.extend(tasks)
                
                # 如果没有获取到任何任务，记录该关键词
                if not tasks:
                    logger.warning(f"关键词 '{query}' 未生成任何处理任务")
                    failed_keywords.append(query)
            except Exception as e:
                logger.error(f"处理关键词 '{query}' 时出错: {str(e)}", exc_info=True)
                failed_keywords.append(query)
        
        # 处理获取到的任务
        try:
            if all_tasks:
                task_count = len(all_tasks)
                link_count = len(all_links)
                logger.info(f"开始处理 {task_count} 个任务，共 {link_count} 个链接")
                
                # 设置任务超时保护
                timeout = 600  # 10分钟超时
                try:
                    # 使用asyncio.wait_for添加整体超时保护
                    results = await asyncio.wait_for(
                        asyncio.gather(*all_tasks, return_exceptions=True),
                        timeout=timeout
                    )
                    
                    # 检查执行结果
                    successful_tasks = 0
                    exceptions = []
                    
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            logger.error(f"任务 {i+1}/{task_count} 执行失败: {type(result).__name__}: {str(result)}")
                            exceptions.append(result)
                        else:
                            successful_tasks += 1
                    
                    # 总结执行结果
                    if exceptions:
                        logger.warning(f"定时爬虫任务中有 {len(exceptions)}/{task_count} 个任务发生异常")
                    
                    logger.info(f"定时爬虫任务完成，成功执行 {successful_tasks}/{task_count} 个任务")
                    
                except asyncio.TimeoutError:
                    logger.error(f"定时爬虫任务执行超时 (超过 {timeout} 秒)，强制终止")
                    # 注意：此处只记录超时，实际任务仍在后台执行
            else:
                logger.warning("定时爬虫任务未生成任何处理任务")
                
            # 记录失败的关键词
            if failed_keywords:
                logger.warning(f"以下关键词处理失败或未生成任务: {', '.join(failed_keywords)}")
                
            # 记录总执行时间
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.info(f"定时爬虫任务执行完成，总耗时: {duration:.2f} 秒")
            
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
