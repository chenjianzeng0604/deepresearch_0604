"""
聊天系统数据库表结构定义（会话、消息、记忆以及用户认证相关）
"""
import hashlib
import logging

logger = logging.getLogger(__name__)

CHAT_SCHEMA = {
    # 会话表
    "sessions": """
        CREATE TABLE IF NOT EXISTS sessions (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36),
            title VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'active'
        )
    """,
    
    # 消息表
    "messages": """
        CREATE TABLE IF NOT EXISTS messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            session_id VARCHAR(36),
            role VARCHAR(20),
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    
    # 用户表
    "users": """
        CREATE TABLE IF NOT EXISTS users (
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
    """
}

def init_chat_default_data(connection):
    """初始化聊天系统默认数据"""
    try:
        with connection.cursor() as cursor:
            # 检查是否已有用户
            cursor.execute("SELECT COUNT(*) as count FROM users")
            result = cursor.fetchone()
            
            # 如果没有用户，创建默认测试用户
            if result and result['count'] == 0:
                password_hash = hashlib.md5("123456".encode()).hexdigest()
                cursor.execute(
                    """
                    INSERT INTO users 
                    (phone, username, password, email, is_active) 
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    ("13800138000", "admin", password_hash, "admin@example.com", True)
                )
                logger.info("已创建默认测试用户")
            
        connection.commit()
    except Exception as e:
        logger.error(f"初始化默认数据失败: {str(e)}")
        connection.rollback()
