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
            phone VARCHAR(20) UNIQUE NOT NULL,
            username VARCHAR(50) NULL,
            password VARCHAR(255) NOT NULL,
            email VARCHAR(100),
            display_name VARCHAR(100),
            is_active BOOLEAN DEFAULT TRUE,
            last_login TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """,
    
    # 验证码表
    "verification_codes": """
        CREATE TABLE IF NOT EXISTS verification_codes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            phone VARCHAR(20) NOT NULL,
            code VARCHAR(10) NOT NULL,
            purpose ENUM('register', 'login', 'reset') NOT NULL,
            is_used BOOLEAN DEFAULT FALSE,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_active_code (phone, purpose, is_used)
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
    """,
    
    # 场景与平台关联表（多对多关系）
    "crawler_scenario_platforms": """
        CREATE TABLE IF NOT EXISTS crawler_scenario_platforms (
            id INT AUTO_INCREMENT PRIMARY KEY,
            scenario_id INT NOT NULL,
            platform_id INT NOT NULL,
            priority INT DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (scenario_id) REFERENCES crawler_scenarios(id) ON DELETE CASCADE,
            FOREIGN KEY (platform_id) REFERENCES crawler_platforms(id) ON DELETE CASCADE,
            UNIQUE KEY unique_scenario_platform (scenario_id, platform_id)
        )
    """,
    
    # 场景与URL格式关联表（多对多关系）
    "crawler_scenario_url_formats": """
        CREATE TABLE IF NOT EXISTS crawler_scenario_url_formats (
            id INT AUTO_INCREMENT PRIMARY KEY,
            scenario_id INT NOT NULL,
            url_format_id INT NOT NULL,
            priority INT DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (scenario_id) REFERENCES crawler_scenarios(id) ON DELETE CASCADE,
            FOREIGN KEY (url_format_id) REFERENCES crawler_url_formats(id) ON DELETE CASCADE,
            UNIQUE KEY unique_scenario_url_format (scenario_id, url_format_id)
        )
    """,
    
    # 聊天会话表
    "chat_sessions": """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id VARCHAR(50) PRIMARY KEY,
            user_id INT NOT NULL,
            title VARCHAR(255) DEFAULT '未命名会话',
            last_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES crawler_admin_users(id) ON DELETE CASCADE
        )
    """,
    
    # 聊天消息表
    "chat_messages": """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            session_id VARCHAR(50) NOT NULL,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
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
                    (phone, password, email, is_active) 
                    VALUES (%s, %s, %s, %s)
                    """,
                    ("13800138000", default_password, "admin@example.com", True)
                )
                connection.commit()
                logger.info("已创建默认管理员账户 (手机号: 13800138000, 密码: admin123)")
        return True
    except Exception as e:
        logger.error(f"初始化爬虫默认数据失败: {str(e)}")
        return False
