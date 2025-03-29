import os
import logging
from datetime import datetime


def setup_logging(app_name="app", log_level=logging.INFO):
    """
    设置统一的日志配置
    
    Args:
        app_name: 应用名称，用于日志文件命名
        log_level: 日志级别
        
    Returns:
        logger: 配置好的日志器
    """
    # 确保日志目录存在
    os.makedirs("data/logs", exist_ok=True)
    
    # 配置日志
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.join("data", "logs", f"{app_name}.log"), encoding="utf-8")
        ]
    )
    
    # 返回日志器
    return logging.getLogger(app_name)
