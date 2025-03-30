#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
后台管理系统 Web应用
可以在开发工具中直接点击启动运行
"""
import os
import sys
import hashlib
from pathlib import Path
import asyncio
import threading
from flask import Flask, render_template, redirect, url_for, flash, request, session, Blueprint
from asgiref.wsgi import WsgiToAsgi
from dotenv import load_dotenv
import uvicorn

FILE_PATH = Path(__file__).resolve()
ROOT_DIR = FILE_PATH.parent.parent.parent
sys.path.append(str(ROOT_DIR))

os.chdir(str(ROOT_DIR))

from src.utils.log_utils import setup_logging
from src.admin.admin_blueprint import admin

# 加载环境变量
env_path = os.path.join(ROOT_DIR, '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    print(f"警告: 环境变量文件不存在: {env_path}")

logger = setup_logging(app_name="app")

# 辅助函数 - 密码哈希
def hash_password(password):
    """使用SHA-256对密码进行哈希"""
    return hashlib.sha256(password.encode()).hexdigest()

# =============== 应用初始化 ===============
def create_app():
    """创建并配置Flask应用实例"""
    # 创建Flask应用
    app = Flask(__name__, 
                template_folder=os.path.join(ROOT_DIR, 'templates'),
                static_folder=os.path.join(ROOT_DIR, 'static'))
    # 设置会话密钥
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev_secret_key')
    # 配置应用程序
    app.config['JSON_AS_ASCII'] = False  # 确保JSON响应能正确处理中文
    app.config['TEMPLATES_AUTO_RELOAD'] = True  # 自动重新加载模板
    # 注册admin蓝图
    app.register_blueprint(admin, url_prefix='/admin')
    return app

# 初始化定时爬虫任务
def init_scheduled_crawler():
    """初始化并启动定时爬虫任务"""
    def start_crawler_scheduler():
        try:
            # 创建事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 初始化定时爬虫
            from src.tools.crawler.scheduled_crawler import ScheduledCrawler
            crawler = ScheduledCrawler()
            
            # 加载并调度任务
            async def init_tasks():
                # 启动调度器
                crawler.scheduler.start()
                logger.info("定时爬虫调度器已启动")
                
                # 加载数据库中的任务
                loaded = await crawler.load_and_schedule_tasks()
                if loaded:
                    logger.info("成功加载定时爬虫任务")
                else:
                    logger.warning("没有找到活跃的定时爬虫任务")
            
            # 运行初始化
            loop.run_until_complete(init_tasks())
            
            # 保持事件循环运行
            loop.run_forever()
        except Exception as e:
            logger.error(f"初始化定时爬虫任务失败: {str(e)}")
    
    # 在后台线程中启动定时任务
    scheduler_thread = threading.Thread(target=start_crawler_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("定时爬虫后台线程已启动")

if __name__ == "__main__":
    init_scheduled_crawler()
    print("\n深度研究助手 - 管理版\n")
    print("启动Web服务器...")
    print("访问 http://127.0.0.1:5000/ 开始使用")
    uvicorn.run(WsgiToAsgi(create_app()), host="127.0.0.1", port=5000)