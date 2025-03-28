"""
对话系统客户端用户管理模块
"""
import hashlib
import random
import string
import logging
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import pymysql
import jwt
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# 用户验证模型
class UserLogin(BaseModel):
    phone: str
    code: str

class UserRegister(BaseModel):
    phone: str
    code: str
    password: str
    email: Optional[str] = None
    username: Optional[str] = None
    
class PhoneVerification(BaseModel):
    phone: str
    purpose: str
    
class PasswordReset(BaseModel):
    phone: str
    code: str
    new_password: str

# 创建路由器
client_auth_router = APIRouter(prefix="/api/client", tags=["client_auth"])

class ClientUserManager:
    """客户端用户管理类"""
    
    def __init__(self, connection):
        """
        初始化客户端用户管理器
        
        Args:
            connection: 数据库连接对象
        """
        self.connection = connection
        self.SECRET_KEY = None  # 将在set_jwt_secret中设置
        
    def set_jwt_secret(self, secret_key: str):
        """设置JWT密钥"""
        self.SECRET_KEY = secret_key
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """
        根据ID获取用户信息
        
        Args:
            user_id: 用户ID
            
        Returns:
            用户信息字典或None
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM client_users WHERE id = %s",
                    (user_id,)
                )
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"根据ID获取用户信息失败: {str(e)}")
            return None
    
    def get_user_by_phone(self, phone: str) -> Optional[Dict]:
        """
        根据手机号获取用户信息
        
        Args:
            phone: 手机号
            
        Returns:
            用户信息字典或None
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM client_users WHERE phone = %s",
                    (phone,)
                )
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"根据手机号获取用户信息失败: {str(e)}")
            return None
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """
        根据用户名获取用户信息
        
        Args:
            username: 用户名
            
        Returns:
            用户信息字典或None
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM client_users WHERE username = %s",
                    (username,)
                )
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"根据用户名获取用户信息失败: {str(e)}")
            return None
    
    def authenticate_user(self, phone: str, password: str) -> Optional[Dict]:
        """
        验证用户登录
        
        Args:
            phone: 手机号
            password: 密码（明文，会被自动哈希）
            
        Returns:
            成功则返回用户信息，失败返回None
        """
        try:
            password_hash = hashlib.md5(password.encode()).hexdigest()
            
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, phone, username FROM client_users WHERE phone = %s AND password = %s AND is_active = TRUE",
                    (phone, password_hash)
                )
                user = cursor.fetchone()
                
                if user:
                    # 更新最后登录时间
                    cursor.execute(
                        "UPDATE client_users SET last_login = NOW() WHERE id = %s",
                        (user['id'],)
                    )
                    self.connection.commit()
                
                return user
        except Exception as e:
            logger.error(f"用户验证失败: {str(e)}")
            return None
    
    def register_user(self, phone: str, password: str, username: str = None, email: str = None) -> Optional[int]:
        """
        注册新用户
        
        Args:
            phone: 手机号
            password: 密码（明文，会被自动哈希）
            username: 用户名（可选）
            email: 邮箱（可选）
            
        Returns:
            成功返回用户ID，失败返回None
        """
        try:
            # 检查手机号是否已存在
            if self.get_user_by_phone(phone):
                logger.warning(f"注册失败：手机号 {phone} 已存在")
                return None
            
            # 检查用户名是否已存在（如果提供）
            if username and self.get_user_by_username(username):
                logger.warning(f"注册失败：用户名 {username} 已存在")
                return None
            
            # 对密码进行MD5哈希
            password_hash = hashlib.md5(password.encode()).hexdigest()
            
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO client_users 
                    (phone, username, password, email, is_active) 
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (phone, username, password_hash, email, True)
                )
                self.connection.commit()
                
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"用户注册失败: {str(e)}")
            self.connection.rollback()
            return None
    
    def update_user(self, user_id: int, username: str = None, email: str = None, 
                      phone: str = None, is_active: bool = True) -> bool:
        """
        更新用户信息
        
        Args:
            user_id: 用户ID
            username: 新用户名（可选）
            email: 新邮箱（可选）
            phone: 新手机号（可选）
            is_active: 是否激活
            
        Returns:
            成功返回True，失败返回False
        """
        try:
            # 检查用户是否存在
            if not self.get_user_by_id(user_id):
                logger.warning(f"更新失败：用户ID {user_id} 不存在")
                return False
                
            # 构建更新字段
            update_fields = []
            params = []
            
            if username is not None:
                update_fields.append("username = %s")
                params.append(username)
                
            if email is not None:
                update_fields.append("email = %s")
                params.append(email)
                
            if phone is not None:
                # 检查新手机号是否已被使用
                existing_user = self.get_user_by_phone(phone)
                if existing_user and existing_user['id'] != user_id:
                    logger.warning(f"更新失败：手机号 {phone} 已被其他用户使用")
                    return False
                    
                update_fields.append("phone = %s")
                params.append(phone)
                
            update_fields.append("is_active = %s")
            params.append(is_active)
            
            params.append(user_id)  # WHERE条件参数
            
            # 执行更新
            with self.connection.cursor() as cursor:
                query = f"UPDATE client_users SET {', '.join(update_fields)} WHERE id = %s"
                cursor.execute(query, params)
                self.connection.commit()
                
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"更新用户信息失败: {str(e)}")
            self.connection.rollback()
            return False
    
    def delete_user(self, user_id: int) -> bool:
        """
        删除用户
        
        Args:
            user_id: 用户ID
            
        Returns:
            成功返回True，失败返回False
        """
        try:
            # 检查用户是否存在
            with self.connection.cursor() as cursor:
                check_query = "SELECT id FROM client_users WHERE id = %s"
                cursor.execute(check_query, (user_id,))
                if not cursor.fetchone():
                    logger.warning(f"删除失败：用户ID {user_id} 不存在")
                    return False
                
                # 执行删除操作
                query = "DELETE FROM client_users WHERE id = %s"
                cursor.execute(query, (user_id,))
                self.connection.commit()
                
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除用户失败: {str(e)}")
            self.connection.rollback()
            return False
    
    def change_password(self, user_id: int, new_password: str) -> bool:
        """
        更改用户密码
        
        Args:
            user_id: 用户ID
            new_password: 新密码（明文，会被自动哈希）
            
        Returns:
            成功返回True，失败返回False
        """
        try:
            # 对新密码进行MD5哈希
            password_hash = hashlib.md5(new_password.encode()).hexdigest()
            
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE client_users SET password = %s WHERE id = %s",
                    (password_hash, user_id)
                )
                self.connection.commit()
                
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"更改密码失败: {str(e)}")
            self.connection.rollback()
            return False
    
    def reset_password_by_phone(self, phone: str, new_password: str) -> bool:
        """
        通过手机号重置密码
        
        Args:
            phone: 手机号
            new_password: 新密码（明文，会被自动哈希）
            
        Returns:
            成功返回True，失败返回False
        """
        try:
            # 检查用户是否存在
            user = self.get_user_by_phone(phone)
            if not user:
                logger.warning(f"重置密码失败：手机号 {phone} 不存在")
                return False
                
            # 对新密码进行MD5哈希
            password_hash = hashlib.md5(new_password.encode()).hexdigest()
            
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE client_users SET password = %s WHERE phone = %s",
                    (password_hash, phone)
                )
                self.connection.commit()
                
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"重置密码失败: {str(e)}")
            self.connection.rollback()
            return False
    
    def get_all_users(self) -> List[Dict]:
        """
        获取所有用户列表
        
        Returns:
            用户列表
        """
        try:
            with self.connection.cursor() as cursor:
                query = "SELECT * FROM client_users ORDER BY id"
                cursor.execute(query)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取用户列表失败: {str(e)}")
            return []
    
    def generate_verification_code(self, phone: str, purpose: str) -> Optional[str]:
        """
        为手机号生成验证码
        
        Args:
            phone: 手机号
            purpose: 用途，可选值：'register', 'login', 'reset'
            
        Returns:
            成功返回验证码，失败返回None
        """
        try:
            # 生成6位数字验证码
            code = ''.join(random.choices(string.digits, k=6))
            
            # 计算过期时间（15分钟后）
            expires_at = datetime.now() + timedelta(minutes=15)
            
            with self.connection.cursor() as cursor:
                # 先将该手机号之前的同用途未使用验证码标记为已使用
                cursor.execute(
                    """
                    UPDATE verification_codes 
                    SET is_used = TRUE 
                    WHERE phone = %s AND purpose = %s AND is_used = FALSE
                    """,
                    (phone, purpose)
                )
                
                # 插入新验证码
                cursor.execute(
                    """
                    INSERT INTO verification_codes 
                    (phone, code, purpose, expires_at) 
                    VALUES (%s, %s, %s, %s)
                    """,
                    (phone, code, purpose, expires_at)
                )
                self.connection.commit()
                
                return code
        except Exception as e:
            logger.error(f"生成验证码失败: {str(e)}")
            self.connection.rollback()
            return None
    
    def verify_code(self, phone: str, code: str, purpose: str) -> bool:
        """
        验证手机验证码
        
        Args:
            phone: 手机号
            code: 验证码
            purpose: 用途，可选值：'register', 'login', 'reset'
            
        Returns:
            验证成功返回True，失败返回False
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id FROM verification_codes 
                    WHERE phone = %s AND code = %s AND purpose = %s AND is_used = FALSE AND expires_at > NOW()
                    """,
                    (phone, code, purpose)
                )
                
                result = cursor.fetchone()
                if not result:
                    return False
                    
                # 标记验证码为已使用
                cursor.execute(
                    "UPDATE verification_codes SET is_used = TRUE WHERE id = %s",
                    (result['id'],)
                )
                self.connection.commit()
                
                return True
        except Exception as e:
            logger.error(f"验证码验证失败: {str(e)}")
            return False
    
    def send_sms_code(self, phone: str, code: str) -> bool:
        """
        发送短信验证码（模拟）
        
        Args:
            phone: 手机号
            code: 验证码
            
        Returns:
            bool: 是否发送成功
        """
        # 实际环境中应对接SMS服务商API
        logger.info(f"模拟发送短信验证码: {code} 到手机号: {phone}")
        return True
        
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        """
        创建JWT访问令牌
        
        Args:
            data: 要编码的数据
            expires_delta: 过期时间增量
            
        Returns:
            str: JWT令牌
        """
        if not self.SECRET_KEY:
            raise ValueError("JWT SECRET_KEY not set")
            
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.SECRET_KEY, algorithm="HS256")
        return encoded_jwt

# 全局管理器实例
_CLIENT_USER_MANAGER: Optional[ClientUserManager] = None

def get_client_user_manager():
    """
    获取客户端用户管理器的依赖函数
    
    Returns:
        ClientUserManager: 客户端用户管理器实例
    """
    global _CLIENT_USER_MANAGER
    if _CLIENT_USER_MANAGER is None:
        raise ValueError("ClientUserManager not initialized")
    return _CLIENT_USER_MANAGER

def initialize_client_user_manager(connection, secret_key: str):
    """
    初始化客户端用户管理器
    
    Args:
        connection: 数据库连接
        secret_key: JWT密钥
    """
    global _CLIENT_USER_MANAGER
    _CLIENT_USER_MANAGER = ClientUserManager(connection)
    _CLIENT_USER_MANAGER.set_jwt_secret(secret_key)

# 路由处理函数
@client_auth_router.post("/send_verification_code")
async def send_verification_code(data: PhoneVerification, client_manager: ClientUserManager = Depends(get_client_user_manager)):
    """
    发送客户端用户验证码
    
    Args:
        data: 包含手机号和用途的请求数据
        client_manager: 客户端用户管理器
        
    Returns:
        JSONResponse: 发送结果
    """
    try:
        if data.purpose not in ["register", "login", "reset"]:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "无效的验证码用途"}
            )
            
        # 生成并保存验证码
        code = client_manager.generate_verification_code(data.phone, data.purpose)
        if not code:
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "生成验证码失败"}
            )
            
        # 发送验证码
        if client_manager.send_sms_code(data.phone, code):
            return JSONResponse(
                content={"success": True, "message": "验证码已发送"}
            )
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "发送验证码失败"}
            )
    except Exception as e:
        logger.error(f"发送验证码失败: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"服务器错误: {str(e)}"}
        )

@client_auth_router.post("/login")
async def login(user_data: UserLogin, client_manager: ClientUserManager = Depends(get_client_user_manager)):
    """
    客户端用户登录
    
    Args:
        user_data: 登录请求数据
        client_manager: 客户端用户管理器
        
    Returns:
        JSONResponse: 登录结果
    """
    try:
        # 验证手机验证码
        if not client_manager.verify_code(user_data.phone, user_data.code, "login"):
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "验证码无效或已过期"}
            )
            
        # 获取用户信息
        user = client_manager.get_user_by_phone(user_data.phone)
        if not user:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "用户不存在"}
            )
            
        # 生成JWT令牌
        access_token = client_manager.create_access_token(
            data={"sub": user["username"] or user["phone"], "user_id": user["id"]}
        )
        
        # 设置cookie
        response = JSONResponse(content={"success": True, "message": "登录成功"})
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            max_age=60 * 60 * 24 * 15,  # 15天
            samesite="lax"
        )
        
        return response
    except Exception as e:
        logger.error(f"登录失败: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"服务器错误: {str(e)}"}
        )

@client_auth_router.post("/register")
async def register(user_data: UserRegister, client_manager: ClientUserManager = Depends(get_client_user_manager)):
    """
    客户端用户注册
    
    Args:
        user_data: 注册请求数据
        client_manager: 客户端用户管理器
        
    Returns:
        JSONResponse: 注册结果
    """
    try:
        # 验证手机验证码
        if not client_manager.verify_code(user_data.phone, user_data.code, "register"):
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "验证码无效或已过期"}
            )
            
        # 检查用户是否已存在
        if client_manager.get_user_by_phone(user_data.phone):
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "该手机号已注册"}
            )
            
        # 注册新用户
        user_id = client_manager.register_user(
            phone=user_data.phone,
            password=user_data.password,
            username=user_data.username,
            email=user_data.email
        )
        
        if user_id:
            return JSONResponse(
                content={"success": True, "message": "注册成功", "user_id": user_id}
            )
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "注册失败"}
            )
    except Exception as e:
        logger.error(f"注册失败: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"服务器错误: {str(e)}"}
        )

@client_auth_router.post("/logout")
async def logout():
    """
    客户端用户登出
    
    Returns:
        JSONResponse: 登出结果
    """
    response = JSONResponse(content={"success": True, "message": "登出成功"})
    response.delete_cookie(key="access_token")
    return response

@client_auth_router.post("/reset_password")
async def reset_password(data: PasswordReset, client_manager: ClientUserManager = Depends(get_client_user_manager)):
    """
    重置客户端用户密码
    
    Args:
        data: 重置密码数据
        client_manager: 客户端用户管理器
        
    Returns:
        JSONResponse: 重置结果
    """
    try:
        # 验证手机验证码
        if not client_manager.verify_code(data.phone, data.code, "reset"):
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "验证码无效或已过期"}
            )
            
        # 重置密码
        if client_manager.reset_password_by_phone(data.phone, data.new_password):
            return JSONResponse(
                content={"success": True, "message": "密码重置成功"}
            )
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "密码重置失败"}
            )
    except Exception as e:
        logger.error(f"密码重置失败: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"服务器错误: {str(e)}"}
        )
