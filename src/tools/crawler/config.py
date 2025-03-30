"""
爬虫模块配置
"""
import logging
from src.admin.crawler_config_manager import crawler_config_manager

logger = logging.getLogger(__name__)

class CrawlerConfig:
    def __init__(self):
        """爬虫配置"""
        # 初始化数据库配置管理器
        try:
            self.db_manager = crawler_config_manager
            logger.info("爬虫配置管理器初始化成功")
        except Exception as e:
            logger.error(f"爬虫配置管理器初始化失败: {str(e)}")
            self._init_fallback_config()
            return
            
        # 获取默认场景
        default_scenario = self.db_manager.get_default_scenario()
        if default_scenario:
            self.default_scenario = default_scenario['name']
        else:
            self.default_scenario = "general"
            
        # 获取所有场景
        all_scenarios = self.db_manager.get_all_scenarios()
        self.supported_scenarios = [s['name'] for s in all_scenarios]
        
        # 场景到Milvus集合的映射关系
        self.scenario_to_collection = {}
        for scenario in all_scenarios:
            self.scenario_to_collection[scenario['name']] = scenario['collection_name']
            
        # 场景搜索URL格式（按场景组织）
        self.scenario_search_url_formats = {}
        for scenario_name in self.supported_scenarios:
            self.scenario_search_url_formats[scenario_name] = self.db_manager.get_url_formats_by_scenario_name(scenario_name)
            
        # 场景直接爬取URL列表（按场景组织）
        self.scenario_search_url = {}
        for scenario_name in self.supported_scenarios:
            self.scenario_search_url[scenario_name] = self.db_manager.get_direct_urls_by_scenario_name(scenario_name)
    
    def _init_fallback_config(self):
        """初始化备用配置（数据库连接失败时使用）"""
        logger.warning("使用备用配置初始化爬虫配置")
        # 定义默认场景
        self.default_scenario = "general"
        # 定义支持的场景列表
        self.supported_scenarios = ["general", "healthcare", "ai"]
        # 场景到Milvus集合的映射关系
        self.scenario_to_collection = {
            "general": "DEEPRESEARCH_GENERAL",
            "healthcare": "DEEPRESEARCH_HEALTHCARE",
            "ai": "DEEPRESEARCH_AI"
        }
        # 按场景组织的网站搜索URL模板
        self.scenario_search_url_formats = {
            # 通用场景
            "general": {
                # Google搜索
                'google.com': "https://www.google.com/search?q={}",
                # Bing搜索
                'bing.com': "https://www.bing.com/search?q={}"
            },
            # 医疗场景
            "healthcare": {
                # Google搜索
                'google.com': "https://www.google.com/search?q={}",
                # Bing搜索
                'bing.com': "https://www.bing.com/search?q={}"
            },
            # AI场景
            "ai": {
                # OpenAI
                'openai.com': "https://openai.com/search/?q={}",
                # InfoQ
                'infoq.com': "https://www.infoq.com/search.action?queryString={}&searchOrder=date",
                # Meta
                'ai.meta.com': "https://ai.meta.com/results/?q={}",
                # 维基百科
                'wikipedia.org': "https://en.wikipedia.org/wiki/{}",
                # Google搜索
                'google.com': "https://www.google.com/search?q={}",
                # Bing搜索
                'bing.com': "https://www.bing.com/search?q={}"
            }
        }
        # 按场景组织的直接爬取URL列表
        self.scenario_search_url = {
            "general": [],
            "ai": [
                "https://openai.com/research/index/",
                "https://openai.com/stories/",
                "https://openai.com/news/",
                "https://www.infoq.com/ai-ml-data-eng/",
                "https://www.anthropic.com/research",
                "https://www.anthropic.com/customers",
                "https://www.anthropic.com/news",
                "https://deepmind.google/research/",
                "https://deepmind.google/discover/blog/",
                "https://ai.meta.com/research/",
                "https://ai.meta.com/blog/"
            ],
            "healthcare": []
        }
    
    def get_search_url_formats(self, scenario=None):
        """获取指定场景的搜索URL格式配置
        
        Args:
            scenario: 场景名称，为None时使用默认场景
            
        Returns:
            dict: 搜索URL格式配置
        """
        scenario = scenario or self.default_scenario
        if scenario not in self.supported_scenarios:
            scenario = self.default_scenario
            
        # 如果有数据库连接，实时获取最新配置
        if hasattr(self, 'db_manager'):
            try:
                return self.db_manager.get_url_formats_by_scenario_name(scenario)
            except Exception as e:
                logger.error(f"获取{scenario}场景URL格式失败: {str(e)}")
                
        return self.scenario_search_url_formats.get(scenario, {})
    
    def get_search_url(self, scenario=None):
        """获取指定场景的直接爬取URL列表
        
        Args:
            scenario: 场景名称，为None时使用默认场景
            
        Returns:
            list: 直接爬取URL列表
        """
        scenario = scenario or self.default_scenario
        if scenario not in self.supported_scenarios:
            scenario = self.default_scenario
            
        # 如果有数据库连接，实时获取最新配置
        if hasattr(self, 'db_manager'):
            try:
                return self.db_manager.get_direct_urls_by_scenario_name(scenario)
            except Exception as e:
                logger.error(f"获取{scenario}场景直接爬取URL失败: {str(e)}")
                
        return self.scenario_search_url.get(scenario, [])
    
    def get_collection_name(self, scenario=None):
        """获取指定场景对应的Milvus集合名称
        
        Args:
            scenario: 场景名称，为None时使用默认场景
            
        Returns:
            str: Milvus集合名称
        """
        scenario = scenario or self.default_scenario
        if scenario not in self.supported_scenarios:
            scenario = self.default_scenario
        
        # 如果有数据库连接，实时获取最新配置
        if hasattr(self, 'db_manager'):
            try:
                scenario_obj = self.db_manager.get_scenario_by_name(scenario)
                if scenario_obj:
                    return scenario_obj['collection_name']
            except Exception as e:
                logger.error(f"获取{scenario}场景集合名称失败: {str(e)}")
                
        return self.scenario_to_collection.get(scenario, self.scenario_to_collection[self.default_scenario])
    
    def get_available_platforms(self) -> list:
        """获取所有可用的爬取平台
        
        Returns:
            list: 可用平台列表
        """
        if hasattr(self, 'db_manager'):
            try:
                platforms = self.db_manager.get_all_platforms()
                return [p['name'] for p in platforms]
            except Exception as e:
                logger.error(f"获取可用平台列表失败: {str(e)}")
        return []

crawler_config = CrawlerConfig()