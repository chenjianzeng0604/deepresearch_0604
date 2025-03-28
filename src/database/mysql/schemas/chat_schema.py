"""
聊天系统数据库表结构定义（会话、消息、记忆相关）
"""

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
    """
}
