"""
邮件发送器工厂模块
提供创建EmailSender实例的工厂方法
"""
import logging
from src.tools.distribution.email_sender import EmailSender

logger = logging.getLogger(__name__)

def create_email_sender() -> EmailSender:
    """
    创建邮件发送器
    
    Returns:
        EmailSender: 邮件发送器实例
    """
    try:
        email_sender = EmailSender()
        if email_sender._check_config():
            logger.info("邮件发送器创建成功")
        else:
            logger.warning("邮件配置不完整，部分功能可能不可用")
        return email_sender
    except Exception as e:
        logger.error(f"创建邮件发送器失败: {str(e)}")
        return None
