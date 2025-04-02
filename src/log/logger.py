import os
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 日志配置
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
# 修改日志目录，去掉data层级
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")

# 确保日志目录存在
Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

def setup_logger(name, log_file=None, level=None):
    """
    配置并返回一个logger实例
    
    Args:
        name: logger名称
        log_file: 日志文件名（可选）
        level: 日志级别（可选）
        
    Returns:
        logging.Logger: 配置好的logger实例
    """
    # 使用传入的级别或默认级别
    log_level = level or LOG_LEVEL
    
    # 创建logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level))
    
    # 如果logger已经有处理器，不再添加
    if logger.handlers:
        return logger
    
    # 创建格式化器
    formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    
    # 添加控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 如果指定了日志文件，添加文件处理器
    if log_file:
        log_path = os.path.join(LOG_DIR, log_file)
        
        # 使用RotatingFileHandler限制文件大小和数量
        file_handler = RotatingFileHandler(
            log_path, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

# 创建应用程序主日志记录器
def get_app_logger():
    """获取应用程序主日志记录器"""
    return setup_logger("deepresearch", "app.log")

# 创建API日志记录器
def get_api_logger():
    """获取API日志记录器"""
    return setup_logger("deepresearch.api", "api.log")

# 创建代理日志记录器
def get_agent_logger():
    """获取代理日志记录器"""
    return setup_logger("deepresearch.agent", "agent.log")

# 创建LLM日志记录器
def get_llm_logger():
    """获取LLM日志记录器"""
    return setup_logger("deepresearch.llm", "llm.log")
