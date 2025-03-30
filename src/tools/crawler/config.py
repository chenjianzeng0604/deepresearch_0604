"""
爬虫模块配置
"""
import logging
from src.admin.crawler_config_manager import crawler_config_manager

logger = logging.getLogger(__name__)

class CrawlerConfig:
    def __init__(self):
        """爬虫配置"""

    def get_default_scenario(self):
        return crawler_config_manager.get_default_scenario()

    def get_search_url_formats(self, scenario=None):
        """获取指定场景的搜索URL格式配置
        
        Args:
            scenario: 场景名称，为None时使用默认场景
            
        Returns:
            dict: 搜索URL格式配置
        """
        if not scenario:
            scenario = self.get_default_scenario()
        return crawler_config_manager.get_url_formats_by_scenario_name(scenario)
    
    def get_search_url(self, scenario=None):
        """获取指定场景的直接爬取URL列表
        
        Args:
            scenario: 场景名称，为None时使用默认场景
            
        Returns:
            list: 直接爬取URL列表
        """
        if not scenario:
            scenario = self.get_default_scenario()
        return crawler_config_manager.get_direct_urls_by_scenario_name(scenario)
    
    def get_collection_name(self, scenario=None):
        """获取指定场景对应的Milvus集合名称
        
        Args:
            scenario: 场景名称，为None时使用默认场景
            
        Returns:
            str: Milvus集合名称
        """
        if not scenario:
            scenario = self.get_default_scenario()
        scenario_obj = crawler_config_manager.get_scenario_by_name(scenario)
        if scenario_obj:
            return scenario_obj['collection_name']
        else:
            return 'DEEPRESEARCH_GENERAL'
    
    def get_available_platforms(self) -> list:
        """获取所有可用的爬取平台
        
        Returns:
            list: 可用平台列表
        """
        platforms = crawler_config_manager.get_all_platforms()
        return [p['name'] for p in platforms]

crawler_config = CrawlerConfig()