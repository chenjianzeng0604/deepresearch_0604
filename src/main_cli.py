#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import asyncio
import logging
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# 将项目根目录添加到Python路径
ROOT_DIR = Path(__file__).parent.parent
sys.path.append(str(ROOT_DIR))

# 确保终端显示中文
import io
import locale
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from src.core.news_processor import NewsProcessor
from src.models.config import AppConfig
from src.distribution.factory import create_distribution_manager
from src.utils.formatters import format_report

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join("data", "logs", "app.log"), encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# 确保必要的目录存在
os.makedirs("data/logs", exist_ok=True)
os.makedirs("data/reports", exist_ok=True)
os.makedirs("data/reports/images", exist_ok=True)
os.makedirs("data/knowledge_base", exist_ok=True)

async def generate_report_cmd(args):
    """
    生成科技分析报告
    
    Args:
        args: 命令行参数
    """
    try:
        logger.info(f"开始生成报告: {args.topic}")
        processor = NewsProcessor(config=AppConfig.from_env())
        async for update in processor.process_tech_news_stream(
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
        processor = NewsProcessor(config=AppConfig.from_env())
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
        processor = NewsProcessor(config=config)
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

def setup_parser():
    """
    设置命令行参数解析器
    
    Returns:
        argparse.ArgumentParser: 参数解析器
    """
    parser = argparse.ArgumentParser(description="深度研究助手 - 命令行版")
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # 生成报告
    generate_parser = subparsers.add_parser("generate", help="生成深度研究报告")
    generate_parser.add_argument("topic", help="报告主题")
    generate_parser.add_argument("--distribute", action="store_true", help="生成后分发报告")
    generate_parser.add_argument("--platforms", nargs="+", help="分发平台列表")
    
    # 列出报告
    list_parser = subparsers.add_parser("list", help="列出报告")
    list_parser.add_argument("--limit", type=int, default=10, help="最大列出数量 (默认: 10)")
    
    # 分发报告
    distribute_parser = subparsers.add_parser("distribute", help="分发报告")
    distribute_parser.add_argument("id", help="报告ID")
    distribute_parser.add_argument("--platforms", nargs="+", help="分发平台列表")
    
    return parser

async def main():
    parser = setup_parser()
    args = parser.parse_args()
    if args.command == "generate":
        async for update in generate_report_cmd(args):
            print(update)
    elif args.command == "list":
        await list_reports_cmd(args)
    elif args.command == "distribute":
        await distribute_report_cmd(report_id=args.id, platforms=args.platforms)
    else:
        parser.print_help()

if __name__ == "__main__":
    print("\n深度研究助手 - 命令行版\n")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n操作已取消")
    except Exception as e:
        logger.error(f"程序执行出错: {e}", exc_info=True)
        print(f"错误: {e}")
