"""
爬虫配置管理器 - 集合名称识别模块
"""
import os
import logging

logger = logging.getLogger(__name__)

# 默认场景
DEFAULT_SCENARIO = "general"

# 场景集合映射
SCENARIO_COLLECTIONS = {
    # 通用知识类别
    "general": "deepresearch_general",
    # 技术类别
    "technology": "deepresearch_technology",
    # 医学类别
    "medical": "deepresearch_medical"
}

class CrawlerConfigManager:
    """简化后的爬虫配置管理器，仅保留集合名称识别功能"""
    
    def __init__(self):
        pass
    
    def get_default_scenario(self):
        """获取默认场景名称"""
        return DEFAULT_SCENARIO
    
    def get_collection_name(self, scenario=None):
        """获取指定场景对应的Milvus集合名称
        
        Args:
            scenario: 场景名称，为None时使用默认场景
            
        Returns:
            str: Milvus集合名称
        """
        # 如果是None，使用默认场景
        if not scenario:
            scenario = self.get_default_scenario()
        
        # 标准化场景名称（转为小写）
        scenario_lower = scenario.lower()
        
        # 如果存在直接映射，返回映射结果
        if scenario_lower in SCENARIO_COLLECTIONS:
            return SCENARIO_COLLECTIONS[scenario_lower]
            
        # 如果不存在映射，返回默认集合
        logger.info(f"未找到场景 '{scenario}' 的映射，使用默认集合: {SCENARIO_COLLECTIONS[DEFAULT_SCENARIO]}")
        return SCENARIO_COLLECTIONS[DEFAULT_SCENARIO]

# 创建单例实例
crawler_config_manager = CrawlerConfigManager()

# 直接提供一个crawler_config导出以兼容现有代码
crawler_config = crawler_config_manager
