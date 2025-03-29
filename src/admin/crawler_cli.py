#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import asyncio
import sys
import json
import argparse
import logging
import asyncio
from pathlib import Path

# 将项目根目录添加到Python路径
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.append(str(ROOT_DIR))

# 确保终端显示中文
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from src.admin.crawler_processor import CrawlerProcessor
from src.config.app_config import AppConfig
from src.tools.distribution.factory import create_distribution_manager
from src.tools.crawler.scheduled_crawler import start_scheduler, stop_scheduler
from src.tools.crawler.config import CrawlerConfig

# 加载环境变量
load_dotenv()

# 设置日志
from src.utils.log_utils import setup_logging
logger = setup_logging(app_name="crawler_cli")

# 确保必要的目录存在
from src.utils.file_utils import ensure_app_directories
ensure_app_directories()

async def generate_report_cmd(args):
    """
    生成科技分析报告
    
    Args:
        args: 命令行参数
    """
    try:
        logger.info(f"开始生成报告: {args.topic}")
        processor = CrawlerProcessor(config=AppConfig.from_env())
        async for update in processor.process_crawl_stream(
            topic=args.topic,
            include_platforms = ["web_site", "search", "github", "arxiv", "weibo", "weixin", "twitter"]
        ):
            yield update
    except Exception as e:
        logger.error(f"生成报告失败: {e}", exc_info=True)
        print(f"错误: {e}")

async def list_reports_cmd(args):
    """
    列出报告
    
    Args:
        args: 命令行参数
    """
    try:
        processor = CrawlerProcessor(config=AppConfig.from_env())
        reports = await processor.list_reports(
            limit=args.limit,
            filter_type=args.type
        )
        if reports:
            print("\n科技分析报告列表:")
            print("-" * 80)
            print(f"{'ID':<36} | {'标题':<30} | {'类型':<15} | {'创建时间':<20}")
            print("-" * 80)
            
            for report in reports:
                report_id = report.get('id', 'N/A')
                title = report.get('title', 'N/A')
                report_type = report.get('type', 'N/A')
                created_at = report.get('created_at', 'N/A')
                
                # 截断过长的标题
                if len(title) > 28:
                    title = title[:25] + "..."
                
                print(f"{report_id:<36} | {title:<30} | {report_type:<15} | {created_at:<20}")
            
            print("-" * 80)
        else:
            print("\n没有找到报告")
    
    except Exception as e:
        logger.error(f"列出报告失败: {e}", exc_info=True)
        print(f"错误: {e}")

async def distribute_report_cmd(report_id=None, platforms=None):
    """
    分发报告
    
    Args:
        report_id: 报告ID
        platforms: 指定的平台列表
    """
    try:
        config = AppConfig.from_env()
        processor = CrawlerProcessor(config=config)
        distribution_manager = create_distribution_manager(config.distribution)
        report = await processor.get_report(report_id)
        if not report:
            print(f"\n未找到ID为 {report_id} 的报告")
            return
        
        if not platforms:
            platforms = distribution_manager.get_enabled_platforms()
        
        if not platforms:
            print("\n没有配置或启用任何分发平台")
            return
        
        print(f"\n开始分发报告 '{report_id}' 到以下平台: {', '.join(platforms)}")
        
        # 执行分发
        results = await distribution_manager.distribute(report, platforms)
        
        # 显示分发结果
        print("\n分发结果:")
        print("-" * 80)
        for platform, result in results.items():
            status = "成功" if result.get('status') == 'success' else "失败"
            message = result.get('message', 'N/A')
            print(f"{platform:<20} | {status:<10} | {message}")
        print("-" * 80)
        
    except Exception as e:
        logger.error(f"分发报告失败: {e}", exc_info=True)
        print(f"错误: {e}")

async def start_crawler_cmd(args):
    """
    启动定时爬虫任务
    
    Args:
        args: 命令行参数
    """
    try:
        keywords = args.keywords
        run_now = args.run_now
        scenario = args.scenario if hasattr(args, 'scenario') else None
        
        print(f"\n启动定时爬虫任务，关键词：{keywords}")
        print(f"场景配置: {scenario}")
        
        if run_now:
            print("\n同时执行一次立即爬取")
        
        crawler_config = CrawlerConfig()
        if not scenario:
            scenario = crawler_config.default_scenario
        
        scheduler = await start_scheduler(keywords, scenario, run_now)
        
        if scheduler:
            print("\n定时爬虫任务已成功启动！")
            print("\n程序将继续在后台运行，可以使用Ctrl+C终止")
            print("或者使用命令 'python -m src.admin.crawler_cli scheduler-stop' 停止任务")
            
            # 保持程序运行，直到按下Ctrl+C
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\n接收到终止信号，正在停止...")
                await stop_scheduler()
                print("已停止定时爬虫任务")
    except Exception as e:
        logger.error(f"启动定时爬虫任务失败: {e}", exc_info=True)
        print(f"错误: {e}")

async def stop_crawler_cmd(args):
    """
    停止定时爬虫任务
    
    Args:
        args: 命令行参数
    """
    try:
        print("\n正在停止定时爬虫任务...")
        result = await stop_scheduler()
        if result:
            print("已成功停止定时爬虫任务")
        else:
            print("没有正在运行的定时爬虫任务或停止失败")
    except Exception as e:
        logger.error(f"停止定时爬虫任务失败: {e}", exc_info=True)
        print(f"错误: {e}")

def setup_parser():
    """
    设置命令行参数解析器
    
    Returns:
        argparse.ArgumentParser: 参数解析器
    """
    parser = argparse.ArgumentParser(description="深度研究爬虫工具 - 命令行界面")
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # 生成报告命令
    report_parser = subparsers.add_parser('report', help='生成科技分析报告')
    report_parser.add_argument('topic', help='报告主题')
    
    # 列出报告命令
    list_parser = subparsers.add_parser('list', help='列出已生成的报告')
    list_parser.add_argument('--limit', type=int, default=10, help='列出的最大数量')
    list_parser.add_argument('--type', help='报告类型过滤')
    
    # 分发报告命令
    distribute_parser = subparsers.add_parser('distribute', help='分发报告到平台')
    distribute_parser.add_argument('report_id', help='报告ID')
    distribute_parser.add_argument('--platforms', nargs='+', help='指定分发平台列表')
    
    # 启动定时爬虫命令
    scheduler_parser = subparsers.add_parser('scheduler-start', help='启动定时爬虫任务')
    scheduler_parser.add_argument('keywords', help='爬取关键词，多个关键词用逗号分隔')
    scheduler_parser.add_argument('--scenario', help='爬取场景配置')
    scheduler_parser.add_argument('--run-now', action='store_true', help='立即执行一次爬取')
    
    # 停止定时爬虫命令
    subparsers.add_parser('scheduler-stop', help='停止定时爬虫任务')
    
    return parser

async def main():
    """主函数"""
    parser = setup_parser()
    args = parser.parse_args()
    
    if args.command == 'report':
        async for update in generate_report_cmd(args):
            print(update)
    elif args.command == 'list':
        await list_reports_cmd(args)
    elif args.command == 'distribute':
        await distribute_report_cmd(args.report_id, args.platforms)
    elif args.command == 'scheduler-start':
        await start_crawler_cmd(args)
    elif args.command == 'scheduler-stop':
        await stop_crawler_cmd(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    print("\n深度研究爬虫工具 - 命令行版\n")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序已被用户中断")
    except Exception as e:
        logger.error(f"运行时错误: {e}", exc_info=True)
        print(f"\n发生错误: {e}")
    finally:
        print("\n程序已退出")
