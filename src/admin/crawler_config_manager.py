"""
爬虫配置数据库管理模块，提供爬虫配置的存储和管理功能
"""

import os
import logging
import json
import hashlib
from typing import Dict, List, Any, Optional, Union
from src.database.mysql.mysql_base import MySQLBase
from src.database.mysql.schemas.crawler_schema import CRAWLER_SCHEMA

logger = logging.getLogger(__name__)

class CrawlerConfigManager(MySQLBase):
    """爬虫配置数据库管理类，提供爬虫配置的存储和管理功能"""
    
    def __init__(self):
        """初始化MySQL连接并确保所需表存在"""
        super().__init__() 
        self._init_crawler_tables()  # 确保爬虫表存在
        self._init_default_data()    # 初始化默认数据
    
    def initialize_database(self):
        """初始化数据库（用于应用启动时检查）"""
        # 这个方法主要是为了兼容之前的代码调用，实际初始化已在__init__中完成
        logger.info("爬虫配置数据库已初始化")
        return True
    
    def _init_crawler_tables(self):
        """初始化爬虫配置相关数据表"""
        try:
            with self.connection.cursor() as cursor:
                for table_name, create_table_sql in CRAWLER_SCHEMA.items():
                    cursor.execute(create_table_sql)
                logger.info("爬虫配置数据表初始化成功")
        except Exception as e:
            logger.error(f"爬虫配置数据表初始化失败: {str(e)}")
            raise
    
    def _init_default_data(self):
        """初始化默认数据"""
        try:
            # 初始化默认管理员账户
            self._init_admin_user()
            
            # 检查是否已有默认场景
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM crawler_scenarios")
                if cursor.fetchone()['count'] == 0:
                    # 添加默认场景
                    default_scenarios = [
                        {
                            "name": "general",
                            "display_name": "通用场景",
                            "description": "通用爬虫场景，适用于一般性技术资讯",
                            "collection_name": "docs_general",
                            "is_default": True
                        },
                        {
                            "name": "ai",
                            "display_name": "人工智能",
                            "description": "人工智能相关资讯，包括机器学习、深度学习、NLP等",
                            "collection_name": "docs_ai",
                            "is_default": False
                        },
                        {
                            "name": "web3",
                            "display_name": "Web3",
                            "description": "Web3相关资讯，包括区块链、NFT、DAO等",
                            "collection_name": "docs_web3",
                            "is_default": False
                        },
                        {
                            "name": "healthcare",
                            "display_name": "医疗健康",
                            "description": "医疗健康相关资讯，包括医疗技术、健康管理等",
                            "collection_name": "docs_healthcare",
                            "is_default": False
                        }
                    ]
                    
                    for scenario in default_scenarios:
                        cursor.execute(
                            """
                            INSERT INTO crawler_scenarios
                            (name, display_name, description, collection_name, is_default)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (
                                scenario["name"],
                                scenario["display_name"],
                                scenario["description"],
                                scenario["collection_name"],
                                scenario["is_default"]
                            )
                        )
                    
                    # 添加默认URL格式
                    self._add_default_url_formats()
                    
                    # 添加默认平台
                    self._add_default_platforms()
                    
                    self.connection.commit()
                    logger.info("已添加默认爬虫场景配置")
            
            return True
        except Exception as e:
            logger.error(f"初始化默认数据失败: {str(e)}")
            return False
            
    def _init_admin_user(self):
        """初始化管理员用户"""
        try:
            with self.connection.cursor() as cursor:
                # 检查是否有管理员账户
                cursor.execute("SELECT COUNT(*) as count FROM crawler_admin_users")
                if cursor.fetchone()['count'] == 0:
                    # 创建默认管理员账户
                    default_username = os.environ.get('DEFAULT_ADMIN_USERNAME', 'admin')
                    default_password = os.environ.get('DEFAULT_ADMIN_PASSWORD', 'admin123')
                    hashed_password = hashlib.sha256(default_password.encode()).hexdigest()
                    
                    cursor.execute(
                        """
                        INSERT INTO crawler_admin_users 
                        (username, password, email, is_active) 
                        VALUES (%s, %s, %s, %s)
                        """,
                        (default_username, hashed_password, "admin@example.com", True)
                    )
                    self.connection.commit()
                    logger.info(f"已创建默认管理员账户: {default_username}")
            return True
        except Exception as e:
            logger.error(f"初始化管理员账户失败: {str(e)}")
            return False
    
    def _add_default_url_formats(self):
        """添加默认URL格式配置"""
        try:
            with self.connection.cursor() as cursor:
                # 获取场景ID
                scenarios = {}
                cursor.execute("SELECT id, name FROM crawler_scenarios")
                for scenario in cursor.fetchall():
                    scenarios[scenario["name"]] = scenario["id"]
                
                # 默认URL格式配置
                default_url_formats = {
                    "general": {
                        "google.com": "https://www.google.com/search?q={}",
                        "bing.com": "https://www.bing.com/search?q={}"
                    },
                    "healthcare": {
                        "google.com": "https://www.google.com/search?q={}+healthcare",
                        "pubmed": "https://pubmed.ncbi.nlm.nih.gov/?term={}"
                    },
                    "ai": {
                        "openai.com": "https://openai.com/search/?q={}",
                        "infoq.com": "https://www.infoq.com/search.action?queryString={}&searchOrder=date",
                        "ai.meta.com": "https://ai.meta.com/results/?q={}",
                        "arxiv": "https://arxiv.org/search/?query={}&searchtype=all"
                    },
                    "web3": {
                        "google.com": "https://www.google.com/search?q={}+web3",
                        "etherscan.io": "https://etherscan.io/search?q={}"
                    }
                }
                
                # 添加URL格式到数据库
                for scenario_name, formats in default_url_formats.items():
                    if scenario_name in scenarios:
                        for platform, url_pattern in formats.items():
                            cursor.execute(
                                """
                                INSERT INTO crawler_url_formats 
                                (scenario_id, platform, name, url_pattern, extraction_method, is_active) 
                                VALUES (%s, %s, %s, %s, %s, %s)
                                """,
                                (
                                    scenarios[scenario_name],
                                    platform,
                                    f"{platform} Search",
                                    url_pattern,
                                    "selenium",
                                    True
                                )
                            )
                
                # 添加直接爬取URL
                default_direct_urls = {
                    "ai": [
                        {"url": "https://openai.com/research/index/", "title": "OpenAI Research"},
                        {"url": "https://openai.com/stories/", "title": "OpenAI Stories"},
                        {"url": "https://openai.com/news/", "title": "OpenAI News"},
                        {"url": "https://www.infoq.com/ai-ml-data-eng/", "title": "InfoQ AI/ML"},
                        {"url": "https://ai.meta.com/research/", "title": "Meta AI Research"},
                        {"url": "https://ai.meta.com/blog/", "title": "Meta AI Blog"}
                    ],
                    "web3": [
                        {"url": "https://ethereum.org/en/blog/", "title": "Ethereum Blog"},
                        {"url": "https://blog.web3.foundation/", "title": "Web3 Foundation Blog"}
                    ]
                }
                
                for scenario_name, urls in default_direct_urls.items():
                    if scenario_name in scenarios:
                        for url_data in urls:
                            cursor.execute(
                                """
                                INSERT INTO crawler_direct_urls 
                                (scenario_id, url, title, description) 
                                VALUES (%s, %s, %s, %s)
                                """,
                                (
                                    scenarios[scenario_name],
                                    url_data["url"],
                                    url_data["title"],
                                    f"{scenario_name}场景直接爬取URL: {url_data['title']}"
                                )
                            )
                
                logger.info("已添加默认URL格式和直接URL配置")
        except Exception as e:
            logger.error(f"添加默认URL格式失败: {str(e)}")
            raise
    
    def _add_default_platforms(self):
        """添加默认平台配置"""
        try:
            with self.connection.cursor() as cursor:
                # 默认平台配置
                default_platforms = [
                    {"name": "web_site", "display_name": "网站搜索", "description": "一般网站搜索", "base_url": "https://www.google.com"},
                    {"name": "github", "display_name": "GitHub", "description": "GitHub代码搜索", "base_url": "https://github.com"},
                    {"name": "arxiv", "display_name": "ArXiv", "description": "ArXiv论文搜索", "base_url": "https://arxiv.org"},
                    {"name": "stackoverflow", "display_name": "Stack Overflow", "description": "Stack Overflow问答搜索", "base_url": "https://stackoverflow.com"},
                    {"name": "news", "display_name": "新闻", "description": "新闻搜索", "base_url": "https://news.google.com"},
                    {"name": "wechat", "display_name": "微信公众号", "description": "微信公众号搜索", "base_url": "https://weixin.sogou.com"},
                    {"name": "hackernews", "display_name": "Hacker News", "description": "Hacker News搜索", "base_url": "https://news.ycombinator.com"},
                    {"name": "medium", "display_name": "Medium", "description": "Medium博客搜索", "base_url": "https://medium.com"},
                    {"name": "pubmed", "display_name": "PubMed", "description": "医学文献搜索", "base_url": "https://pubmed.ncbi.nlm.nih.gov"}
                ]
                
                # 添加平台到数据库
                for platform in default_platforms:
                    cursor.execute(
                        """
                        INSERT INTO crawler_platforms 
                        (name, display_name, description, base_url, is_active) 
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            platform["name"],
                            platform["display_name"],
                            platform["description"],
                            platform.get("base_url", ""),
                            True
                        )
                    )
                
                logger.info("已添加默认平台配置")
        except Exception as e:
            logger.error(f"添加默认平台失败: {str(e)}")
            raise

    # 场景相关方法
    def get_all_scenarios(self):
        """获取所有场景"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM crawler_scenarios ORDER BY is_default DESC, name")
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取场景列表失败: {str(e)}")
            return []
    
    def get_scenario(self, scenario_id):
        """获取单个场景"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM crawler_scenarios WHERE id = %s", (scenario_id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"获取场景失败: {str(e)}")
            return None
    
    def get_scenario_by_name(self, scenario_name):
        """通过名称获取场景"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM crawler_scenarios WHERE name = %s", (scenario_name,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"通过名称获取场景失败: {str(e)}")
            return None
    
    def get_default_scenario(self):
        """获取默认场景"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM crawler_scenarios WHERE is_default = TRUE LIMIT 1")
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"获取默认场景失败: {str(e)}")
            return None
    
    def get_scenario_by_id(self, scenario_id):
        """通过ID获取场景（兼容方法）"""
        return self.get_scenario(scenario_id)
    
    def add_scenario(self, name, display_name, description="", collection_name=None, is_default=False):
        """添加场景"""
        try:
            # 如果新场景设为默认，先将所有场景的默认标志设为False
            with self.connection.cursor() as cursor:
                if is_default:
                    cursor.execute("UPDATE crawler_scenarios SET is_default = FALSE")
                
                cursor.execute(
                    """
                    INSERT INTO crawler_scenarios 
                    (name, display_name, description, collection_name, is_default) 
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (name, display_name, description, collection_name, is_default)
                )
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"添加场景失败: {str(e)}")
            return None
    
    def update_scenario(self, scenario_id, display_name=None, description=None, 
                        collection_name=None, is_default=None, is_active=None):
        """更新场景"""
        try:
            # 构建更新语句和参数
            update_parts = []
            params = []
            
            if display_name is not None:
                update_parts.append("display_name = %s")
                params.append(display_name)
                
            if description is not None:
                update_parts.append("description = %s")
                params.append(description)
                
            if collection_name is not None:
                update_parts.append("collection_name = %s")
                params.append(collection_name)
                
            if is_active is not None:
                update_parts.append("is_active = %s")
                params.append(is_active)
            
            if not update_parts:
                return False
                
            with self.connection.cursor() as cursor:
                # 构建并执行更新语句
                sql = f"UPDATE crawler_scenarios SET {', '.join(update_parts)} WHERE id = %s"
                params.append(scenario_id)
                cursor.execute(sql, tuple(params))
                
                # 如果需要设置为默认场景
                if is_default:
                    self.set_default_scenario(scenario_id)
                
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"更新场景失败: {str(e)}")
            return False
    
    def set_default_scenario(self, scenario_id):
        """设置默认场景"""
        try:
            with self.connection.cursor() as cursor:
                # 先将所有场景设置为非默认
                cursor.execute("UPDATE crawler_scenarios SET is_default = FALSE")
                
                # 再将指定场景设置为默认
                cursor.execute("UPDATE crawler_scenarios SET is_default = TRUE WHERE id = %s", (scenario_id,))
                self.connection.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"设置默认场景失败: {str(e)}")
            return False
    
    def delete_scenario(self, scenario_id):
        """删除场景"""
        try:
            with self.connection.cursor() as cursor:
                # 检查是否为默认场景
                cursor.execute("SELECT is_default FROM crawler_scenarios WHERE id = %s", (scenario_id,))
                scenario = cursor.fetchone()
                
                if not scenario:
                    return False
                
                # 不允许删除默认场景
                if scenario['is_default']:
                    logger.warning("不能删除默认场景")
                    return False
                
                cursor.execute("DELETE FROM crawler_scenarios WHERE id = %s", (scenario_id,))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除场景失败: {str(e)}")
            return False
    
    # URL格式相关方法
    def get_url_formats(self, scenario_id=None):
        """获取URL格式列表"""
        try:
            with self.connection.cursor() as cursor:
                if scenario_id:
                    sql = """
                        SELECT uf.*, s.name as scenario_name, s.display_name as scenario_display_name 
                        FROM crawler_url_formats uf 
                        JOIN crawler_scenarios s ON uf.scenario_id = s.id 
                        WHERE uf.scenario_id = %s
                        ORDER BY uf.platform
                    """
                    cursor.execute(sql, (scenario_id,))
                else:
                    sql = """
                        SELECT uf.*, s.name as scenario_name, s.display_name as scenario_display_name 
                        FROM crawler_url_formats uf 
                        JOIN crawler_scenarios s ON uf.scenario_id = s.id 
                        ORDER BY s.name, uf.platform
                    """
                    cursor.execute(sql)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取URL格式列表失败: {str(e)}")
            return []
    
    def get_url_formats_by_scenario_name(self, scenario_name):
        """通过场景名称获取URL格式"""
        try:
            with self.connection.cursor() as cursor:
                sql = """
                    SELECT uf.* 
                    FROM crawler_url_formats uf 
                    JOIN crawler_scenarios s ON uf.scenario_id = s.id 
                    WHERE s.name = %s
                    ORDER BY uf.platform
                """
                cursor.execute(sql, (scenario_name,))
                formats = cursor.fetchall()
                
                # 将结果转换为字典格式，与原先的配置格式保持一致
                result = {}
                for item in formats:
                    result[item['platform']] = item['url_format']
                    
                return result
        except Exception as e:
            logger.error(f"通过场景名称获取URL格式失败: {str(e)}")
            return {}
    
    def get_url_formats_by_scenario(self, scenario_id):
        """通过场景ID获取URL格式列表"""
        try:
            with self.connection.cursor() as cursor:
                sql = """
                    SELECT uf.*, s.name as scenario_name, s.display_name as scenario_display_name 
                    FROM crawler_url_formats uf 
                    JOIN crawler_scenarios s ON uf.scenario_id = s.id 
                    WHERE uf.scenario_id = %s
                    ORDER BY uf.platform
                """
                cursor.execute(sql, (scenario_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"通过场景ID获取URL格式列表失败: {str(e)}")
            return []
    
    def add_url_format(self, scenario_id, platform, url_format, description=None):
        """添加URL格式"""
        try:
            with self.connection.cursor() as cursor:
                # 检查是否已存在相同场景和平台的记录
                cursor.execute(
                    "SELECT id FROM crawler_url_formats WHERE scenario_id = %s AND platform = %s",
                    (scenario_id, platform)
                )
                existing = cursor.fetchone()
                
                if existing:
                    # 更新现有记录
                    cursor.execute(
                        """
                        UPDATE crawler_url_formats 
                        SET url_format = %s, description = %s, is_active = TRUE 
                        WHERE id = %s
                        """,
                        (url_format, description, existing['id'])
                    )
                    return existing['id']
                else:
                    # 添加新记录
                    cursor.execute(
                        """
                        INSERT INTO crawler_url_formats 
                        (scenario_id, platform, url_format, description) 
                        VALUES (%s, %s, %s, %s)
                        """,
                        (scenario_id, platform, url_format, description)
                    )
                    return cursor.lastrowid
        except Exception as e:
            logger.error(f"添加URL格式失败: {str(e)}")
            return None
    
    def update_url_format(self, url_format_id, platform=None, url_format=None, description=None, is_active=None):
        """更新URL格式"""
        try:
            # 构建更新语句和参数
            update_parts = []
            params = []
            
            if platform is not None:
                update_parts.append("platform = %s")
                params.append(platform)
                
            if url_format is not None:
                update_parts.append("url_format = %s")
                params.append(url_format)
                
            if description is not None:
                update_parts.append("description = %s")
                params.append(description)
                
            if is_active is not None:
                update_parts.append("is_active = %s")
                params.append(is_active)
            
            if not update_parts:
                return False
                
            with self.connection.cursor() as cursor:
                # 构建并执行更新语句
                sql = f"UPDATE crawler_url_formats SET {', '.join(update_parts)} WHERE id = %s"
                params.append(url_format_id)
                cursor.execute(sql, tuple(params))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"更新URL格式失败: {str(e)}")
            return False
    
    def get_url_format_by_id(self, url_format_id):
        """通过ID获取URL格式"""
        try:
            with self.connection.cursor() as cursor:
                sql = """
                    SELECT uf.*, s.name as scenario_name, s.display_name as scenario_display_name 
                    FROM crawler_url_formats uf 
                    JOIN crawler_scenarios s ON uf.scenario_id = s.id 
                    WHERE uf.id = %s
                """
                cursor.execute(sql, (url_format_id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"通过ID获取URL格式失败: {str(e)}")
            return None
    
    def delete_url_format(self, url_format_id):
        """删除URL格式"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("DELETE FROM crawler_url_formats WHERE id = %s", (url_format_id,))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除URL格式失败: {str(e)}")
            return False
    
    # 直接爬取URL相关方法
    def get_direct_urls(self, scenario_id=None):
        """获取直接爬取URL列表"""
        try:
            with self.connection.cursor() as cursor:
                if scenario_id:
                    sql = """
                        SELECT du.*, s.name as scenario_name 
                        FROM crawler_direct_urls du 
                        JOIN crawler_scenarios s ON du.scenario_id = s.id 
                        WHERE du.scenario_id = %s
                        ORDER BY du.title
                    """
                    cursor.execute(sql, (scenario_id,))
                else:
                    sql = """
                        SELECT du.*, s.name as scenario_name 
                        FROM crawler_direct_urls du 
                        JOIN crawler_scenarios s ON du.scenario_id = s.id 
                        ORDER BY s.name, du.title
                    """
                    cursor.execute(sql)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取直接爬取URL列表失败: {str(e)}")
            return []
    
    def get_direct_urls_by_scenario_name(self, scenario_name):
        """通过场景名称获取直接爬取URL"""
        try:
            with self.connection.cursor() as cursor:
                sql = """
                    SELECT du.url 
                    FROM crawler_direct_urls du 
                    JOIN crawler_scenarios s ON du.scenario_id = s.id 
                    WHERE s.name = %s
                """
                cursor.execute(sql, (scenario_name,))
                urls = cursor.fetchall()
                
                # 将结果转换为列表格式，与原先的配置格式保持一致
                return [item['url'] for item in urls]
        except Exception as e:
            logger.error(f"通过场景名称获取直接爬取URL失败: {str(e)}")
            return []
    
    def add_direct_url(self, scenario_id, url, title=None, description=None):
        """添加直接爬取URL"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO crawler_direct_urls 
                    (scenario_id, url, title, description) 
                    VALUES (%s, %s, %s, %s)
                    """,
                    (scenario_id, url, title, description)
                )
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"添加直接爬取URL失败: {str(e)}")
            return None
    
    def update_direct_url(self, direct_url_id, url=None, title=None, description=None, is_active=None):
        """更新直接爬取URL"""
        try:
            # 构建更新语句和参数
            update_parts = []
            params = []
            
            if url is not None:
                update_parts.append("url = %s")
                params.append(url)
                
            if title is not None:
                update_parts.append("title = %s")
                params.append(title)
                
            if description is not None:
                update_parts.append("description = %s")
                params.append(description)
                
            if is_active is not None:
                update_parts.append("is_active = %s")
                params.append(is_active)
            
            if not update_parts:
                return False
                
            with self.connection.cursor() as cursor:
                # 构建并执行更新语句
                sql = f"UPDATE crawler_direct_urls SET {', '.join(update_parts)} WHERE id = %s"
                params.append(direct_url_id)
                cursor.execute(sql, tuple(params))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"更新直接爬取URL失败: {str(e)}")
            return False
    
    def delete_direct_url(self, direct_url_id):
        """删除直接爬取URL"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("DELETE FROM crawler_direct_urls WHERE id = %s", (direct_url_id,))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除直接爬取URL失败: {str(e)}")
            return False
    
    # 平台相关方法
    def get_all_platforms(self):
        """获取所有平台"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM crawler_platforms ORDER BY name")
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取平台列表失败: {str(e)}")
            return []
    
    def get_platform_by_id(self, platform_id):
        """通过ID获取平台"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM crawler_platforms WHERE id = %s", (platform_id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"获取平台失败: {str(e)}")
            return None
    
    def get_platform_by_name(self, platform_name):
        """通过名称获取平台"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM crawler_platforms WHERE name = %s", (platform_name,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"通过名称获取平台失败: {str(e)}")
            return None
    
    def add_platform(self, name, display_name, description=""):
        """添加平台"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO crawler_platforms 
                    (name, display_name, description, is_active) 
                    VALUES (%s, %s, %s, %s)
                    """,
                    (name, display_name, description, True)
                )
                self.connection.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"添加平台失败: {str(e)}")
            return None
            
    def update_platform(self, platform_id, display_name=None, description=None, base_url=None, is_active=None):
        """更新平台"""
        try:
            # 构建更新语句和参数
            update_parts = []
            params = []
            
            if display_name is not None:
                update_parts.append("display_name = %s")
                params.append(display_name)
                
            if description is not None:
                update_parts.append("description = %s")
                params.append(description)
                
            if base_url is not None:
                update_parts.append("base_url = %s")
                params.append(base_url)
                
            if is_active is not None:
                update_parts.append("is_active = %s")
                params.append(is_active)
            
            if not update_parts:
                return False
                
            # 构建并执行更新语句
            sql = f"UPDATE crawler_platforms SET {', '.join(update_parts)} WHERE id = %s"
            params.append(platform_id)
            
            with self.connection.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                self.connection.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"更新平台失败: {str(e)}")
            return False
    
    def delete_platform(self, platform_id):
        """删除平台"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("DELETE FROM crawler_platforms WHERE id = %s", (platform_id,))
                self.connection.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除平台失败: {str(e)}")
            return False
    
    def toggle_platform_status(self, platform_id):
        """切换平台状态"""
        try:
            with self.connection.cursor() as cursor:
                # 获取当前状态
                cursor.execute("SELECT is_active FROM crawler_platforms WHERE id = %s", (platform_id,))
                platform = cursor.fetchone()
                
                if not platform:
                    return False
                
                # 切换状态
                new_status = not platform['is_active']
                cursor.execute(
                    "UPDATE crawler_platforms SET is_active = %s WHERE id = %s",
                    (new_status, platform_id)
                )
                self.connection.commit()
                return True
        except Exception as e:
            logger.error(f"切换平台状态失败: {str(e)}")
            return False
    
    # 定时爬虫任务管理相关方法
    def get_all_scheduled_tasks(self):
        """获取所有定时爬虫任务"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT t.*, s.name as scenario_name, s.display_name as scenario_display_name 
                    FROM crawler_scheduled_tasks t
                    JOIN crawler_scenarios s ON t.scenario_id = s.id
                    ORDER BY t.created_at DESC
                """)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取定时爬虫任务列表失败: {str(e)}")
            return []
    
    def get_scheduled_task(self, task_id):
        """获取单个定时爬虫任务"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT t.*, s.name as scenario_name, s.display_name as scenario_display_name 
                    FROM crawler_scheduled_tasks t
                    JOIN crawler_scenarios s ON t.scenario_id = s.id
                    WHERE t.id = %s
                """, (task_id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"获取定时爬虫任务失败: {str(e)}")
            return None
    
    def add_scheduled_task(self, task_name, scenario_id, keywords, platforms, 
                          cron_expression, max_concurrent_tasks=3, description="", is_active=False):
        """添加定时爬虫任务"""
        try:
            # 验证场景ID是否存在
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT id FROM crawler_scenarios WHERE id = %s", (scenario_id,))
                if not cursor.fetchone():
                    logger.error(f"场景ID不存在: {scenario_id}")
                    return None
                
                # 将keywords和platforms列表转换为JSON字符串
                keywords_str = json.dumps(keywords, ensure_ascii=False)
                platforms_str = json.dumps(platforms, ensure_ascii=False)
                
                # 执行插入操作
                cursor.execute("""
                    INSERT INTO crawler_scheduled_tasks 
                    (task_name, scenario_id, keywords, platforms, cron_expression, 
                     max_concurrent_tasks, description, is_active) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    task_name, scenario_id, keywords_str, platforms_str, 
                    cron_expression, max_concurrent_tasks, description, is_active
                ))
                self.connection.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"添加定时爬虫任务失败: {str(e)}")
            return None
    
    def update_scheduled_task(self, task_id, task_name=None, scenario_id=None, 
                             keywords=None, platforms=None, cron_expression=None, 
                             max_concurrent_tasks=None, description=None, is_active=None):
        """更新定时爬虫任务"""
        try:
            # 构建更新语句和参数
            update_parts = []
            params = []
            
            if task_name is not None:
                update_parts.append("task_name = %s")
                params.append(task_name)
                
            if scenario_id is not None:
                # 验证场景ID是否存在
                with self.connection.cursor() as cursor:
                    cursor.execute("SELECT id FROM crawler_scenarios WHERE id = %s", (scenario_id,))
                    if not cursor.fetchone():
                        logger.error(f"场景ID不存在: {scenario_id}")
                        return False
                        
                update_parts.append("scenario_id = %s")
                params.append(scenario_id)
                
            if keywords is not None:
                update_parts.append("keywords = %s")
                params.append(json.dumps(keywords, ensure_ascii=False))
                
            if platforms is not None:
                update_parts.append("platforms = %s")
                params.append(json.dumps(platforms, ensure_ascii=False))
                
            if cron_expression is not None:
                update_parts.append("cron_expression = %s")
                params.append(cron_expression)
                
            if max_concurrent_tasks is not None:
                update_parts.append("max_concurrent_tasks = %s")
                params.append(max_concurrent_tasks)
                
            if description is not None:
                update_parts.append("description = %s")
                params.append(description)
                
            if is_active is not None:
                update_parts.append("is_active = %s")
                params.append(is_active)
            
            if not update_parts:
                return False
                
            # 构建并执行更新语句
            sql = f"UPDATE crawler_scheduled_tasks SET {', '.join(update_parts)} WHERE id = %s"
            params.append(task_id)
            
            with self.connection.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                self.connection.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"更新定时爬虫任务失败: {str(e)}")
            return False
    
    def delete_scheduled_task(self, task_id):
        """删除定时爬虫任务"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("DELETE FROM crawler_scheduled_tasks WHERE id = %s", (task_id,))
                self.connection.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除定时爬虫任务失败: {str(e)}")
            return False
    
    def toggle_scheduled_task_status(self, task_id):
        """切换定时爬虫任务状态"""
        try:
            with self.connection.cursor() as cursor:
                # 获取当前状态
                cursor.execute("SELECT is_active FROM crawler_scheduled_tasks WHERE id = %s", (task_id,))
                task = cursor.fetchone()
                
                if not task:
                    return False
                
                # 切换状态
                new_status = not task['is_active']
                cursor.execute(
                    "UPDATE crawler_scheduled_tasks SET is_active = %s WHERE id = %s",
                    (new_status, task_id)
                )
                self.connection.commit()
                return True
        except Exception as e:
            logger.error(f"切换定时爬虫任务状态失败: {str(e)}")
            return False
    
    def update_task_last_run_time(self, task_id):
        """更新任务最后运行时间"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE crawler_scheduled_tasks SET last_run_time = CURRENT_TIMESTAMP WHERE id = %s",
                    (task_id,)
                )
                self.connection.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"更新任务最后运行时间失败: {str(e)}")
            return False
    
    def get_active_tasks(self):
        """获取所有活跃的定时爬虫任务"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT t.*, s.name as scenario_name, s.display_name as scenario_display_name,
                           s.collection_name
                    FROM crawler_scheduled_tasks t
                    JOIN crawler_scenarios s ON t.scenario_id = s.id
                    WHERE t.is_active = TRUE
                    ORDER BY t.created_at DESC
                """)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取活跃定时爬虫任务列表失败: {str(e)}")
            return []
            
    def get_scheduled_task_count(self):
        """获取定时爬虫任务总数"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM crawler_scheduled_tasks")
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            logger.error(f"获取定时爬虫任务总数失败: {str(e)}")
            return 0
    
    def get_active_task_count(self):
        """获取活跃的定时爬虫任务总数"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM crawler_scheduled_tasks WHERE is_active = TRUE")
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            logger.error(f"获取活跃定时爬虫任务总数失败: {str(e)}")
            return 0
    
    # 管理员相关方法
    def verify_admin_login(self, username, password):
        """验证管理员登录"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM crawler_admin_users 
                    WHERE username = %s AND password = %s AND is_active = TRUE
                    """,
                    (username, password)
                )
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"验证管理员登录失败: {str(e)}")
            return None
            
    def check_admin_username_exists(self, username):
        """检查管理员用户名是否已存在"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) as count FROM crawler_admin_users WHERE username = %s",
                    (username,)
                )
                result = cursor.fetchone()
                return result and result['count'] > 0
        except Exception as e:
            logger.error(f"检查管理员用户名是否存在失败: {str(e)}")
            return False
            
    def get_admin_count(self):
        """获取管理员用户数量"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM crawler_admin_users")
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            logger.error(f"获取管理员用户数量失败: {str(e)}")
            return 0
            
    def add_admin_user(self, username, password, email, display_name=None, is_active=True):
        """添加管理员用户"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO crawler_admin_users 
                    (username, password, email, display_name, is_active) 
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (username, password, email, display_name or username, is_active)
                )
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"添加管理员用户失败: {str(e)}")
            return None
            
    def authenticate_admin(self, username, password):
        """验证管理员账号密码"""
        try:
            import hashlib
            hashed_password = hashlib.sha256(password.encode()).hexdigest()
            
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, username FROM crawler_admin_users WHERE username = %s AND password = %s AND is_active = TRUE",
                    (username, hashed_password)
                )
                admin = cursor.fetchone()
                
                if admin:
                    # 更新最后登录时间
                    cursor.execute(
                        "UPDATE crawler_admin_users SET last_login = NOW() WHERE id = %s",
                        (admin['id'],)
                    )
                    return True
                    
                return False
        except Exception as e:
            logger.error(f"管理员认证失败: {str(e)}")
            return False
    
    def get_direct_url_by_id(self, url_id):
        """通过ID获取直接URL信息"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT cdu.*, s.name as scenario_name 
                    FROM crawler_direct_urls cdu
                    JOIN crawler_scenarios s ON cdu.scenario_id = s.id
                    WHERE cdu.id = %s
                    """, 
                    (url_id,)
                )
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"获取直接URL信息失败: {str(e)}")
            return None
    
    # 统计方法 - 用于后台管理界面
    def get_scenario_count(self):
        """获取场景总数"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM crawler_scenarios")
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            logger.error(f"获取场景总数失败: {str(e)}")
            return 0
    
    def get_url_format_count(self):
        """获取URL格式总数"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM crawler_url_formats")
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            logger.error(f"获取URL格式总数失败: {str(e)}")
            return 0
    
    def get_direct_url_count(self):
        """获取直接URL总数"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM crawler_direct_urls")
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            logger.error(f"获取直接URL总数失败: {str(e)}")
            return 0
    
    def get_default_scenario_name(self):
        """获取默认场景名称"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT name FROM crawler_scenarios WHERE is_default = TRUE LIMIT 1")
                result = cursor.fetchone()
                return result['name'] if result else "general"
        except Exception as e:
            logger.error(f"获取默认场景名称失败: {str(e)}")
            return "general"
    
    def get_all_scenarios_with_counts(self):
        """获取所有场景及其URL格式和直接URL数量"""
        try:
            scenarios = self.get_all_scenarios()
            if not scenarios:
                return []
            
            # 获取各场景的URL格式和直接URL数量
            with self.connection.cursor() as cursor:
                for scenario in scenarios:
                    # 获取URL格式数量
                    cursor.execute(
                        "SELECT COUNT(*) as count FROM crawler_url_formats WHERE scenario_id = %s",
                        (scenario['id'],)
                    )
                    result = cursor.fetchone()
                    scenario['url_format_count'] = result['count'] if result else 0
                    
                    # 获取直接URL数量
                    cursor.execute(
                        "SELECT COUNT(*) as count FROM crawler_direct_urls WHERE scenario_id = %s",
                        (scenario['id'],)
                    )
                    result = cursor.fetchone()
                    scenario['direct_url_count'] = result['count'] if result else 0
            
            return scenarios
        except Exception as e:
            logger.error(f"获取场景统计信息失败: {str(e)}")
            return []

    def get_all_url_formats_with_scenario(self):
        """获取所有URL格式，附带完整的场景信息"""
        try:
            with self.connection.cursor() as cursor:
                sql = """
                    SELECT uf.*, 
                           s.id as scenario_id, 
                           s.name as scenario_name, 
                           s.display_name as scenario_display_name,
                           s.description as scenario_description,
                           p.id as platform_id,
                           p.name as platform_name,
                           p.display_name as platform_display_name
                    FROM crawler_url_formats uf 
                    JOIN crawler_scenarios s ON uf.scenario_id = s.id 
                    LEFT JOIN crawler_platforms p ON uf.platform = p.name
                    ORDER BY s.display_name, p.display_name
                """
                cursor.execute(sql)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取URL格式列表失败: {str(e)}")
            return []

    def get_all_direct_urls_with_scenario(self):
        """获取所有直接爬取URL，附带完整的场景信息"""
        try:
            with self.connection.cursor() as cursor:
                sql = """
                    SELECT du.*, 
                           s.id as scenario_id, 
                           s.name as scenario_name, 
                           s.display_name as scenario_display_name,
                           s.description as scenario_description
                    FROM crawler_direct_urls du 
                    JOIN crawler_scenarios s ON du.scenario_id = s.id 
                    ORDER BY s.display_name, du.title
                """
                cursor.execute(sql)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取直接爬取URL列表失败: {str(e)}")
            return []
