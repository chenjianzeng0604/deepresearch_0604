#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
后台管理系统 Web应用
可以在开发工具中直接点击启动运行
"""

import os
import sys
import logging
import hashlib
import pymysql
from pathlib import Path
import asyncio
import threading

# =============== 路径配置 ===============
# 确保在任何环境下都能正确找到项目根目录
FILE_PATH = Path(__file__).resolve()
ROOT_DIR = FILE_PATH.parent.parent.parent
sys.path.append(str(ROOT_DIR))  # 将项目根目录添加到Python路径

# 确保工作目录是项目根目录
os.chdir(str(ROOT_DIR))

# =============== 编码配置 ===============
# 确保终端显示中文
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# =============== 导入依赖 ===============
try:
    from flask import Flask, render_template, redirect, url_for, flash, request
    from dotenv import load_dotenv
except ImportError as e:
    print(f"错误: 缺少必要依赖，请安装: pip install flask python-dotenv pymysql")
    sys.exit(1)

# 导入数据库模块
from src.admin.crawler_config_manager import CrawlerConfigManager

# 加载环境变量
env_path = os.path.join(ROOT_DIR, '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    print(f"警告: 环境变量文件不存在: {env_path}")

# =============== 日志配置 ===============
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger("admin_web")

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
    
    # 导入和注册蓝图
    try:
        from src.admin.admin_blueprint import admin_bp
        app.register_blueprint(admin_bp, url_prefix='/admin')
        logger.info("已注册admin蓝图")
    except Exception as e:
        logger.error(f"注册admin蓝图失败: {str(e)}")
    
    # 根路由 - 重定向到管理登录页面
    @app.route('/')
    def index():
        """重定向到管理登录页面"""
        return redirect(url_for('admin.login'))
    
    # 错误处理
    @app.errorhandler(404)
    def page_not_found(e):
        """404页面"""
        return render_template('admin/error.html', error="页面不存在", message="找不到请求的页面"), 404
    
    @app.errorhandler(500)
    def server_error(e):
        """500页面"""
        return render_template('admin/error.html', error="服务器内部错误", message="服务器处理请求时发生错误"), 500
    
    # 初始化定时爬虫任务（创建函数但不在这里调用，后面会直接调用）
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
    
    return app, init_scheduled_crawler  # 返回应用和初始化函数

# 创建全局应用实例
app, init_crawler = create_app()

# 立即初始化定时爬虫任务（而不是依赖于 before_first_request）
init_crawler()

# =============== 主程序入口 ===============
if __name__ == "__main__":
    import uvicorn
    from uvicorn.middleware.wsgi import WSGIMiddleware
    
    # 使用8080端口避免冲突
    port = 8080
    
    print("\n" + "="*50)
    print("深度研究助手 - 后台管理系统")
    print("="*50)
    
    # 输出环境信息
    print(f"项目根目录: {ROOT_DIR}")
    print(f"Python版本: {sys.version}")
    
    # 启动Web服务器
    print("\n" + "="*50)
    print("Web服务器已启动!")
    print("访问地址:")
    print(f"  • 本地访问: http://127.0.0.1:{port}")
    print(f"  • 网络访问: http://0.0.0.0:{port}")
    print("="*50 + "\n")

    # 使用WSGIMiddleware适配Flask应用
    asgi_app = WSGIMiddleware(app)
    try:
        uvicorn.run(asgi_app, host="0.0.0.0", port=port)
    except OSError as e:
        print(f"启动服务器失败: {e}")
        print("尝试只绑定到本地地址...")
        # 如果绑定到0.0.0.0失败，尝试只绑定到本地地址
        uvicorn.run(asgi_app, host="127.0.0.1", port=port)
