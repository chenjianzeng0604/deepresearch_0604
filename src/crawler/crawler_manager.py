"""
爬虫管理器模块，整合所有专用爬虫，提供统一的接口
"""
from src.crawler.web_crawlers import WebCrawler
from src.crawler.specialized_crawlers import ArxivCrawler, GithubCrawler, WeChatOfficialAccountCrawler
from src.crawler.config import CrawlerConfig

class CrawlerManager:
    """
    爬虫管理器，管理所有专用爬虫，根据URL选择合适的爬虫
    """
    
    def __init__(self):
        """初始化爬虫配置"""
        self.config = CrawlerConfig()
        """初始化爬虫管理器"""
        self.arxiv_crawler = ArxivCrawler()
        self.github_crawler = GithubCrawler()
        self.web_crawler = WebCrawler()
        self.wechat_crawler = WeChatOfficialAccountCrawler()