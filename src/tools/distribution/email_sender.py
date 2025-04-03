"""邮件发送工具类

提供邮件发送功能，支持HTML内容和附件
"""

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import List, Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class EmailSender:
    """邮件发送工具类"""
    def __init__(self):
        """初始化邮件发送工具类"""
        load_dotenv()
        self.smtp_server = os.getenv("EMAIL_SMTP_SERVER")
        self.smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        self.smtp_username = os.getenv("EMAIL_SMTP_USERNAME")
        self.smtp_password = os.getenv("EMAIL_SMTP_PASSWORD")
        self.sender_email = os.getenv("EMAIL_SENDER")
        self.recipient_emails = os.getenv("EMAIL_RECIPIENT").split(",")
        self.use_tls = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
        self._check_config()
    
    def _check_config(self):
        """检查邮件配置是否完整"""
        if not all([self.smtp_server, self.smtp_username, self.smtp_password, self.sender_email]):
            logger.warning("邮件配置不完整，无法发送邮件")
            return False
        return True
    
    async def send_email(self, 
                    subject: str, 
                    body: str, 
                    is_html: bool = True,
                    additional_recipients: List[str] = None):
        """发送邮件
        
        Args:
            subject: 邮件主题
            body: 邮件内容
            is_html: 是否为HTML内容
            additional_recipients: 额外的收件人列表，除了配置文件中指定的收件人外
            
        Returns:
            bool: 是否发送成功
        """
        if not self._check_config():
            return False
        
        # 合并默认收件人和额外收件人
        recipients = list(self.recipient_emails)  # 创建默认收件人的副本
        if additional_recipients:
            for email in additional_recipients:
                if email and isinstance(email, str) and email.strip():
                    email = email.strip()
                    if email not in recipients:
                        recipients.append(email)
        
        if not recipients:
            logger.warning("没有有效的收件人，无法发送邮件")
            return False
            
        success = True
        for recipient_email in recipients:
            try:
                msg = MIMEMultipart()
                msg["From"] = self.sender_email
                msg["To"] = recipient_email
                msg["Subject"] = subject
                content_type = "html" if is_html else "plain"
                msg.attach(MIMEText(body, content_type, "utf-8"))
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    if self.use_tls:
                        server.starttls()
                    server.login(self.smtp_username, self.smtp_password)
                    server.send_message(msg)
                logger.info(f"邮件发送成功: {recipient_email}")
            except smtplib.SMTPResponseException as e:
                if e.smtp_code == -1 and b'\x00\x00\x00' in e.smtp_error:
                    logger.info(f"邮件发送成功(忽略连接关闭阶段的非标准响应): {recipient_email}")
                    pass  
                else:
                    logger.error(f"邮件发送失败: {str(e)}")
                    success = False
            except Exception as e:
                logger.error(f"邮件发送失败: {str(e)}")
                success = False
        
        return success