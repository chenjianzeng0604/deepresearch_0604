"""
爬虫配置数据库表结构定义
"""
import hashlib
import logging

logger = logging.getLogger(__name__)

CRAWLER_SCHEMA = {
    # 管理员用户表
    "crawler_admin_users": """
        CREATE TABLE IF NOT EXISTS crawler_admin_users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            email VARCHAR(100),
            display_name VARCHAR(100),
            is_active BOOLEAN DEFAULT TRUE,
            last_login TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """,
    
    # 爬虫场景表
    "crawler_scenarios": """
        CREATE TABLE IF NOT EXISTS crawler_scenarios (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(50) UNIQUE NOT NULL,
            display_name VARCHAR(100) NOT NULL,
            description TEXT,
            collection_name VARCHAR(100) NOT NULL,
            is_default BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """,
    
    # 爬虫URL格式表（用于下钻子链接）
    "crawler_url_formats": """
        CREATE TABLE IF NOT EXISTS crawler_url_formats (
            id INT AUTO_INCREMENT PRIMARY KEY,
            scenario_id INT NOT NULL,
            platform VARCHAR(50) NOT NULL,
            name VARCHAR(100) NOT NULL,
            url_pattern TEXT NOT NULL,
            extraction_method VARCHAR(50) DEFAULT 'selenium',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (scenario_id) REFERENCES crawler_scenarios(id) ON DELETE CASCADE
        )
    """,
    
    # 直接爬取URL表
    "crawler_direct_urls": """
        CREATE TABLE IF NOT EXISTS crawler_direct_urls (
            id INT AUTO_INCREMENT PRIMARY KEY,
            scenario_id INT NOT NULL,
            url TEXT NOT NULL,
            title VARCHAR(255),
            description TEXT,
            is_processed BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (scenario_id) REFERENCES crawler_scenarios(id) ON DELETE CASCADE
        )
    """,
    
    # 爬虫平台表
    "crawler_platforms": """
        CREATE TABLE IF NOT EXISTS crawler_platforms (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(50) UNIQUE NOT NULL,
            display_name VARCHAR(100) NOT NULL,
            base_url VARCHAR(255),
            description TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """,
    
    # 定时爬虫任务表
    "crawler_scheduled_tasks": """
        CREATE TABLE IF NOT EXISTS crawler_scheduled_tasks (
            id INT AUTO_INCREMENT PRIMARY KEY,
            task_name VARCHAR(100) NOT NULL,
            scenario_id INT NOT NULL,
            keywords TEXT NOT NULL,
            platforms TEXT NOT NULL,
            cron_expression VARCHAR(100) NOT NULL,
            max_concurrent_tasks INT DEFAULT 3,
            description TEXT,
            is_active BOOLEAN DEFAULT FALSE,
            last_run_time TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (scenario_id) REFERENCES crawler_scenarios(id) ON DELETE CASCADE
        )
    """
}

def init_crawler_default_data(connection):
    """初始化爬虫相关的默认数据"""
    try:
        with connection.cursor() as cursor:
            # 检查是否有管理员账户
            cursor.execute("SELECT COUNT(*) as count FROM crawler_admin_users")
            if cursor.fetchone()['count'] == 0:
                # 创建默认管理员账户
                default_password = hashlib.sha256("admin123".encode()).hexdigest()
                cursor.execute(
                    """
                    INSERT INTO crawler_admin_users 
                    (username, password, email, is_active) 
                    VALUES (%s, %s, %s, %s)
                    """,
                    ("admin", default_password, "admin@example.com", True)
                )
                connection.commit()
                logger.info("已创建默认管理员账户 (用户名: admin, 密码: admin123)")
        return True
    except Exception as e:
        logger.error(f"初始化爬虫默认数据失败: {str(e)}")
        return False
