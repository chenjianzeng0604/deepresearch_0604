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
            id VARCHAR(36) PRIMARY KEY,
            session_id VARCHAR(36),
            role VARCHAR(10),
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )
    """,
    
    # 长期记忆表
    "memories": """
        CREATE TABLE IF NOT EXISTS memories (
            id VARCHAR(36) PRIMARY KEY,
            session_id VARCHAR(36),
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )
    """,
    
    # 客户端用户表
    "client_users": """
        CREATE TABLE IF NOT EXISTS client_users (
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
            # 检查是否已有客户端用户
            cursor.execute("SELECT COUNT(*) as count FROM client_users")
            result = cursor.fetchone()
            
            # 如果没有用户，创建默认测试用户
            if result and result['count'] == 0:
                password_hash = hashlib.md5("123456".encode()).hexdigest()
                cursor.execute(
                    """
                    INSERT INTO client_users 
                    (phone, username, password, email, is_active) 
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    ("13800138000", "testuser", password_hash, "test@example.com", True)
                )
                logger.info("已创建默认测试客户端用户")
            
        connection.commit()
    except Exception as e:
        logger.error(f"初始化默认数据失败: {str(e)}")
        connection.rollback()
