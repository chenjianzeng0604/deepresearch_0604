"""
爬虫模块配置
"""
class CrawlerConfig:
    def __init__(self):
        """爬虫配置"""
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
                'openai.com.research': "https://openai.com/research/index/",
                'openai.com.stories': "https://openai.com/stories/",
                'openai.com.news': "https://openai.com/news/",
                'openai.com': "https://openai.com/search/?q={}",
                # InfoQ
                'infoq.com.ai-ml-data-eng': "https://www.infoq.com/ai-ml-data-eng/",
                'infoq.com': "https://www.infoq.com/search.action?queryString={}&searchOrder=date",
                # Anthropic
                'anthropic.com.research': "https://www.anthropic.com/research",
                'anthropic.com.customers': "https://www.anthropic.com/customers",
                'anthropic.com.news': "https://www.anthropic.com/news",
                # Google
                'deepmind.google.research': "https://deepmind.google/research/",
                'deepmind.google.blog': "https://deepmind.google/discover/blog/",
                # Meta
                'ai.meta.com.research': "https://ai.meta.com/research/",
                'ai.meta.com.blog': "https://ai.meta.com/blog/",
                'ai.meta.com': "https://ai.meta.com/results/?q={}",
                # 维基百科
                'wikipedia.org': "https://en.wikipedia.org/wiki/{}",
                # Google搜索
                'google.com': "https://www.google.com/search?q={}",
                # Bing搜索
                'bing.com': "https://www.bing.com/search?q={}"
            },
            # 搜索场景
            "online_search": {
                # Google搜索
                'google.com': "https://www.google.com/search?q={}",
                # Bing搜索
                'bing.com': "https://www.bing.com/search?q={}"
            }
        }
        # 按场景组织的直接爬取URL列表
        self.scenario_search_url = {
            "general": [],
            "ai": [],
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
        
        return self.scenario_to_collection.get(scenario)