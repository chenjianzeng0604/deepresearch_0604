"""
爬虫模块配置
"""
class CrawlerConfig:
    def __init__(self):
        """爬虫配置"""
        # 定义网站搜索URL模板，爬虫将爬取其搜索列表中的URL
        self.search_url_formats = {
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
            # 纯AI新闻站，覆盖技术、伦理、行业应用，信息密度高
            'artificialintelligence-news.com': "https://www.artificialintelligence-news.com/?s={}",
            # 印度及全球AI生态动态，适合关注新兴市场技术落地者。
            'analyticsindiamag.com': "https://analyticsindiamag.com/?s={}",
            # 提供AI/ML开源工具测评、代码教程，适合开发者。
            'marktechpost.com': "https://www.marktechpost.com/?s={}",
            # 强调AI实际应用案例（如医疗、金融），启发商业化思路。
            'unite.ai': "https://www.unite.ai/?s={}",
        }
        # 定义直接爬取的URL
        self.search_url = []