"""
统一科技新闻网站爬虫模块，整合顶级科技和AI新闻网站
"""

import logging
import io
import os
import asyncio
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse, urlunparse, urljoin
from markdownify import markdownify as md
import aiohttp

import asyncio
import logging
import re
import os
from typing import List, Optional
from urllib.parse import urlparse, urljoin, quote
import aiohttp
import requests

from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from aiohttp import ClientSession
from src.database.vectordb.milvus_dao import MilvusDao
import uuid
import json
import pickle
from src.prompts.prompt_templates import PromptTemplates
from datetime import datetime
from src.model.llm_client import LLMClient
from playwright.async_api import async_playwright
from src.tools.crawler.cloudflare_bypass import CloudflareBypass
from src.database.vectordb.schema_manager import MilvusSchemaManager
from src.app.chat_bean import AppConfig
from src.tools.crawler.config import CrawlerConfig
import re
from transformers import pipeline, AutoTokenizer, AutoModelForMaskedLM
import torch

logger = logging.getLogger(__name__)

class WebCrawler:
    """
    常用网站爬虫，支持主流技术媒体
    """
    
    def __init__(self):
        self.config = AppConfig.from_env()
        self.crawler_config = CrawlerConfig()
        # 初始化通用MilvusDao客户端
        self.milvus_dao = MilvusDao(
            uri=os.getenv("MILVUS_URI", "http://localhost:19530"),
            user=os.getenv("MILVUS_USER", ""),
            password=os.getenv("MILVUS_PASSWORD", ""),
            db_name=os.getenv("MILVUS_DB_NAME", "default"),
            reconnect_attempts=int(os.getenv("MILVUS_RECONNECT_ATTEMPTS", "3")),
            reconnect_delay=int(os.getenv("MILVUS_RECONNECT_DELAY", "2"))
        )
        self.proxies = {
            "server": os.getenv("KDL_PROXIES_SERVER", ""),
            "username": os.getenv("KDL_PROXIES_USERNAME", ""),
            "password": os.getenv("KDL_PROXIES_PASSWORD", "")
        }
        self.headers = {
            'User-Agent': UserAgent().random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        self.crawler_extract_pdf_timeout = int(os.getenv("CRAWLER_EXTRACT_PDF_TIMEOUT", 30))
        self.crawler_max_links_result = int(os.getenv("CRAWLER_MAX_LINKS_RESULT", 10))
        self.crawler_fetch_url_timeout = int(os.getenv("CRAWLER_FETCH_URL_TIMEOUT", 60))
        self.crawler_fetch_article_with_semaphore = int(os.getenv("CRAWLER_FETCH_ARTICLE_WITH_SEMAPHORE", 10))
        self.crawler_fetch_url_max_retries = int(os.getenv("CRAWLER_FETCH_URL_MAX_RETRIES", 2))
        self.crawler_fetch_url_retry_delay = int(os.getenv("CRAWLER_FETCH_URL_RETRY_DELAY", 2))
        self.llm_client = LLMClient(api_key=self.config.llm.api_key, 
                                        model=self.config.llm.model, 
                                        api_base=self.config.llm.api_base)
        self.article_trunc_word_count = int(os.getenv("ARTICLE_TRUNC_WORD_COUNT", 10000))
        
    def is_valid_url(self, url: str, base_domain: Optional[str] = None) -> bool:
        """
        检查URL是否有效且应该被爬取
        
        Args:
            url: 要检查的URL
            base_domain: 可选的基础域名限制
            
        Returns:
            bool: URL是否有效且应该被爬取
        """
        parsed = urlparse(url)
        
        # 基础验证
        if parsed.scheme not in ('http', 'https'):
            return False
            
        # 域名限制
        if base_domain and not parsed.netloc.endswith(base_domain):
            return False
        
        # 排除静态文件（图片、视频、压缩包等）
        static_ext = ('.jpg', '.jpeg', '.png', '.gif', '.css', '.js',
                     '.zip', '.tar', '.gz', '.exe', '.svg', '.ico',
                     '.mp3', '.mp4', '.avi', '.mov', '.flv', '.wmv',
                     '.woff', '.woff2', '.ttf', '.eot', '.otf')
        if any(parsed.path.lower().endswith(ext) for ext in static_ext):
            return False

        # 排除低质量内容链接
        low_value_patterns = [
            # 广告、跟踪和分析
            '/ads/', '/ad/', 'doubleclick', 'analytics', 'tracker', 'click.php',
            'pixel.php', 'counter.php', 'utm_', 'adserv', 'banner', 'sponsor',
            # 用户操作和账户页面
            'redirect', 'share', 'login', 'signup', 'register', 'comment', 
            'subscribe', 'newsletter', 'account', 'profile', 'password',
            "/dictionary/", "/translate/", "/grammar/", "/thesaurus/", 
            # 站点信息页
            'privacy', 'terms', 'about-us', 'contact-us', 'faq', 'help',
            'cookie', 'disclaimer', 'copyright', 'license', 'sitemap',
            "contact", "about", "privacy", "disclaimer",
            # 搜索引擎特定页面
            'www.bing.com/images/search', 'google.com/imgres',
            'search?', 'search/', '/search', 'query=', 'www.google.com/maps/search',
            'www.bing.com/translate', 'www.instagram.com/cambridgewords',
            'dictionary.cambridge.org/plus', 'dictionary.cambridge.org/howto.html',
            'www.google.com/shopping', 'support.google.com/googleshopping',
            'www.bing.com/maps', 'www.bing.com/shop', 'go.microsoft.com/fwlink',
            'bingapp.microsoft.com/bing', 'www.google.com/httpservice/retry/enablejs',
            'www.google.com/travel/flights', 'maps.google.com/maps',
            # 社交媒体分享链接
            'facebook.com/sharer', 'twitter.com/intent', 'linkedin.com/share',
            'plus.google.com', 'pinterest.com/pin', 't.me/share',
            # 打印、RSS和其他功能页面
            'print=', 'print/', 'print.html', 'rss', 'feed', 'atom',
            'pdf=', 'pdf/', 'download=', '/download', 'embed=',
            # 日历、存档和分类页面
            'calendar', '/tag/', '/tags/', '/category/', '/categories/',
            '/archive/', '/archives/', '/author/', '/date/',
            # 购物车、结账和交易页面
            'cart', 'checkout', 'basket', 'payment', 'order', 'transaction'
        ]
        if any(pattern in url.lower() for pattern in low_value_patterns):
            return False

        search_engine_home = [
            # 匹配所有Bing主页变体（含参数）
            r'^https?://(www\.)?bing\.com/?(\?.*)?$',
            r'^http?://(www\.)?bing\.com/?(\?.*)?$',
            # 匹配所有Google主页变体（含参数）
            r'^https?://(www\.)?google\.com/?(\?.*)?$'
            r'^http?://(www\.)?google\.com/?(\?.*)?$'
        ]
        for pattern in search_engine_home:
            if re.match(pattern, url, re.I):
                return False
            
        return True
    
    def normalize_url(self, url: str) -> str:
        """
        标准化URL：去除查询参数、锚点和末尾斜杠
        
        Args:
            url: 要标准化的URL
            
        Returns:
            str: 标准化后的URL
        """
        parsed = urlparse(url)
        parsed = parsed._replace(
            query='',
            fragment='',
            path=parsed.path.rstrip('/')
        )
        return urlunparse(parsed)
    
    async def extract_pdf(self, url: str) -> str:
        """
        提取PDF文档内容
        
        Args:
            url: PDF文档URL
            
        Returns:
            Dict[str, Any]: 提取的内容
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=self.crawler_extract_pdf_timeout) as response:
                    if response.status == 200:
                        pdf_content = await response.read()
                        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                            text_content = []
                            laparams = LAParams(
                                detect_vertical=True,  # 检测垂直文本
                                all_texts=True,        # 提取所有文本层
                                line_overlap=0.5,      # 行重叠阈值
                                char_margin=2.0        # 字符间距阈值
                            )
                            for page in pdf.pages:
                                page_text = page.extract_text(laparams=laparams)
                                if page_text:
                                    text_content.append(
                                        page_text.replace('\ufffd', '?')  # 替换非法字符
                                    )
                            if text_content:
                                return '\n\n'.join(text_content)
        except Exception as e:
            logger.error(f"提取PDF内容出错: {url}, 错误: {str(e)}")
        
        return None
    
    async def extract_links(self, html: str, base_url: str) -> List[str]:
        """
        从HTML中提取链接
        
        Args:
            html: HTML内容
            base_url: 基础URL
            
        Returns:
            List[str]: 提取的链接列表
        """
        links = []
        try:
            soup = BeautifulSoup(html, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                absolute_url = urljoin(base_url, href)
                if self.is_valid_url(absolute_url):
                    if absolute_url in links:
                        continue
                    links.append(absolute_url)
        except Exception as e:
            logger.error(f"提取链接出错: {base_url}, 错误: {str(e)}")
        return links

    async def parse_sub_url(self, search_url: str) -> List[str]:
        try:
            html_content = await self.fetch_url_with_proxy_fallback(search_url)
            if not html_content:
                logger.error(f"主URL获取内容为空: {search_url}")
                return []
            return await self.extract_links(html_content, search_url)
        except Exception as e:
            logger.error(f"parse_sub_url出错: {search_url}, 错误: {str(e)}")
            return []
    
    async def fetch_article_and_save2milvus(self, query: str, links: List[str], scenario: str = None) -> List[str]:
        """
        获取文章内容并保存到Milvus
        
        Args:
            query: 搜索查询词
            links: 链接列表
            scenario: 场景名称，为None时使用默认场景
            
        Returns:
            List[str]: 处理结果
        """
        if not links or len(links) == 0:
            logger.warning(f"没有有效链接可爬取，查询：{query}")
            return []
        
        links_to_fetch = await self.filterSavedUrl(links, scenario)
        if not links_to_fetch:
            return []
        
        results = await self.fetch_article(links_to_fetch)
        await self.save_article(results, scenario)
        return results

    async def filterSavedUrl(self, links, scenario: str = None):
        # 获取场景对应的Milvus集合名称
        collection_name = self.crawler_config.get_collection_name(scenario)
        if not collection_name:
            logger.warning(f"未找到场景 {scenario} 对应的Milvus集合名称")
            return []
            
        logger.info(f"过滤已存在URL，场景: {scenario}, 集合: {collection_name}")
        
        # 将链接按批次处理，避免查询字符串过长
        batch_size = 50
        unique_links = list(set(links))  # 去重
        all_existing_urls = set()
        
        for i in range(0, len(unique_links), batch_size):
            batch_links = unique_links[i:i+batch_size]
            url_list_str = ", ".join([f"'{url}'" for url in batch_links])
            filter_expr = f"url in [{url_list_str}]"
            
            try:
                res = self.milvus_dao.query(
                    collection_name=collection_name,
                    filter=filter_expr,
                    output_fields=["url"],
                )
                if res:
                    batch_existing_urls = set(r["url"] for r in res) if res else set()
                    all_existing_urls.update(batch_existing_urls)
            except Exception as e:
                logger.error(f"查询Milvus中的已存在URL失败: {str(e)}")
                # 继续执行，不阻断进程

        links_to_fetch = [link for link in unique_links if link not in all_existing_urls]
        if not links_to_fetch:
            logger.info(f"所有链接 ({len(unique_links)}) 已存在于数据库中，无需重新处理")
            return []
            
        logger.info(f"将处理{len(links_to_fetch)}/{len(unique_links)} 个链接 (过滤掉 {len(all_existing_urls)} 个已存在链接)")
        return links_to_fetch

    async def fetch_article(self, links: List[str]) -> List[str]:
        """
        获取文章内容并保存到Milvus
        
        Args:
            links: 链接列表
        Returns:
            List[str]: 处理结果
        """
        if not links or len(links) == 0:
            logger.warning(f"没有有效链接可爬取")
            return []

        sem = asyncio.Semaphore(self.crawler_fetch_article_with_semaphore)
        async def fetch_article_with_semaphore(link):
            try:
                async with sem:
                    if self.is_pdf_url(link):
                        content = await self.extract_pdf(link)
                        if not content or len(content.strip()) == 0:
                            content = ""
                        return {"url": link, "content": content}
                    else:
                        content = await self.fetch_url_md(link)
                        if not content or len(content.strip()) == 0:
                            content = ""
                        return {"url": link, "content": content}
            except asyncio.CancelledError:
                logger.warning(f"获取文章任务被取消: {link}")
                return {"url": link, "content": "", "error": "Task cancelled"}
            except Exception as e:
                logger.error(f"获取文章失败: {link}, 错误: {str(e)}")
                return {"url": link, "content": "", "error": str(e)}
        
        links_to_process = links[:min(self.crawler_max_links_result, len(links))]
        tasks = [fetch_article_with_semaphore(link) for link in links_to_process]

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results
        except asyncio.CancelledError:
            logger.warning("爬取任务被取消")
            return []
        except Exception as e:
            logger.error(f"获取文章信息时发生错误: {str(e)}")
            return []

    async def save_article(self, results, scenario: str = None):
        # 按批次处理和保存数据，避免单次操作过大
        batch_size = 5
        current_batch = []
        rows = 0

        # 获取场景对应的Milvus集合名称
        collection_name = self.crawler_config.get_collection_name(scenario)
        if not collection_name:
            logger.warning(f"未找到场景 {scenario} 对应的Milvus集合名称")
            return

        links = [r["url"] for r in results if r and "url" in r]
        links_to_save = await self.filterSavedUrl(links, scenario)
        if not links_to_save:
            logger.warning(f"没有需要保存的文章，场景：{scenario}")
            return

        results = [r for r in results if r["url"] in links_to_save]

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"获取文章信息时发生错误: {str(result)}")
                continue
            
            if not result or 'url' not in result:
                logger.warning(f"获取的结果格式不正确: {result}")
                continue
                
            if 'error' in result and result['error']:
                logger.warning(f"获取文章 {result['url']} 失败: {result['error']}")
                continue
                
            if not result['content'] or len(result['content'].strip()) == 0:
                logger.warning(f"获取的文章内容为空: {result['url']}")
                continue
            
            try:
                schema, index_params = MilvusSchemaManager.get_deepresearch_schema()
                contents = self.cut_string_by_length(result['content'], self.article_trunc_word_count)
                
                for content in contents:
                    if not content or len(content.strip()) == 0:
                        continue
                        
                    try:
                        content_embs = self.milvus_dao.generate_embeddings([content])
                        if not content_embs or len(content_embs) == 0:
                            logger.warning(f"为内容生成嵌入向量失败: {result['url']}")
                            continue
                            
                        data_item = {
                            "id": str(uuid.uuid4()),
                            "url": result['url'],
                            "content": content,
                            "content_emb": content_embs[0],
                            "create_time": int(datetime.now(timezone.utc).timestamp() * 1000)
                        }
                        
                        current_batch.append(data_item)
                        
                        if len(current_batch) >= batch_size:
                            try:
                                success = await self.batch_save_to_milvus(
                                    collection_name=collection_name, 
                                    schema=schema, 
                                    index_params=index_params, 
                                    data=current_batch
                                )
                                if success:
                                    rows += len(current_batch)
                                await asyncio.sleep(1)
                            except Exception as e:
                                logger.error(f"写入Milvus失败: {str(e)}")
                            current_batch = []
                    
                    except Exception as e:
                        logger.error(f"处理内容块时出错: {str(e)}")
            
            except Exception as e:
                logger.error(f"处理文章时出错: {result['url']}, {str(e)}")
        
        if current_batch:
            success = await self.batch_save_to_milvus(
                collection_name=collection_name, 
                schema=schema, 
                index_params=index_params, 
                data=current_batch
            )
            if success:
                rows += len(current_batch)
            await asyncio.sleep(1)
    
        logger.info(f"成功写入{rows}行数据到集合 {collection_name}")

    async def batch_save_to_milvus(self, collection_name, schema, index_params, data):
        try:
            success = self.milvus_dao.store(
                collection_name=collection_name, 
                schema=schema, 
                index_params=index_params, 
                data=data
            )
            if not success:
                logger.warning(f"Milvus数据存储失败，批次大小：{len(data)}")
            return success
        except Exception as e:
            logger.error(f"批量写入Milvus失败: {str(e)}")
            return False
    
    def cut_string_by_length(self, s, length):
        """
        将字符串按固定长度切割成数组

        :param s: 需要切割的字符串
        :param length: 每个子字符串的固定长度
        :return: 切割后的子字符串数组
        """
        return [s[i:i+length] for i in range(0, len(s), length)]
    
    def is_pdf_url(self, url: str) -> bool:
        return '/pdf/' in url or url.endswith('.pdf')
    
    async def fetch_url_md(self, url: str) -> Optional[str]:
        """
        获取URL内容
        
        Args:
            url: 要获取的URL
            
        Returns:
            Optional[str]: Markdown内容
        """
        return self.html2md(await self.fetch_url_with_proxy_fallback(url))

    async def fetch_url_with_proxy_fallback(self, url: str) -> Optional[str]:
        """
        尝试获取URL内容，如果不使用代理失败，则尝试使用代理
        
        Args:
            url: 要获取的URL
            
        Returns:
            Optional[str]: 页面内容或None（如果获取失败）
        """
        # 验证URL格式
        if not url or not isinstance(url, str):
            logger.error(f"无效URL: {url}")
            return None
            
        # 确保URL有正确的协议前缀
        if not url.startswith(('http://', 'https://')):
            logger.error(f"URL缺少协议前缀: {url}")
            return None
            
        try:
            logger.info(f"尝试不使用代理获取URL: {url}")
            return await self._fetch_url_implementation(url, useProxy=False)    
        except Exception as e:
            logger.error(f"不使用代理获取URL失败 {url}: {str(e)}")
            try:
                logger.info(f"尝试使用代理获取URL: {url}")
                return await self._fetch_url_implementation(url, useProxy=True)    
            except Exception as e:
                logger.error(f"使用代理获取URL失败 {url}: {str(e)}")
                return None
    
    async def _fetch_url_implementation(self, url: str, useProxy: bool = False) -> Optional[str]:
        try:
            async with async_playwright() as p:
                if useProxy:
                    logger.info(f"Fetching URL {url} with proxy")
                    browser = await p.chromium.launch(
                        headless=True,
                        proxy=self.proxies,
                        args=[
                        "--disable-blink-features=AutomationControlled",
                            "--no-sandbox",
                            "--disable-web-security",
                            "--disable-features=IsolateOrigins,site-per-process",
                            f"--user-agent={UserAgent().random}",
                            "--use-fake-ui-for-media-stream",
                            "--use-fake-device-for-media-stream",
                            "--disable-gpu",
                            "--disable-dev-shm-usage",
                            "--disable-software-rasterizer"
                        ],
                        env={"SSLKEYLOGFILE": "/dev/null"}
                    )
                else:
                    logger.info(f"Fetching URL {url} without proxy")
                    browser = await p.chromium.launch(
                        headless=True,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-sandbox",
                            "--disable-web-security",
                            "--disable-features=IsolateOrigins,site-per-process",
                            f"--user-agent={UserAgent().random}",
                            "--use-fake-ui-for-media-stream",
                            "--use-fake-device-for-media-stream",
                            "--disable-gpu",
                            "--disable-dev-shm-usage",
                            "--disable-software-rasterizer"
                        ],
                        env={"SSLKEYLOGFILE": "/dev/null"}
                    )

                context = await browser.new_context(
                    user_agent=UserAgent().random,
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US,en;q=0.9",
                    timezone_id="America/New_York",
                    permissions=["geolocation"],
                    geolocation={"latitude": 40.7128, "longitude": -74.0060},
                    color_scheme="dark"
                )

                try:
                    await context.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        })
                        window.generateMouseMove = () => {
                            const path = Array.from({length: 20}, () => ({
                                x: Math.random() * window.innerWidth,
                                y: Math.random() * window.innerHeight,
                                duration: Math.random() * 300 + 200
                            }))
                            path.forEach(p => {
                                window.dispatchEvent(new MouseEvent('mousemove', p))
                            })
                        }
                    """)

                    page = await context.new_page()

                    await page.route("**/*", lambda route: route.abort() 
                        if route.request.resource_type in {"image", "media", "stylesheet", "font"}
                        else route.continue_()
                    )

                    await page.goto(
                        url, 
                        wait_until="domcontentloaded", 
                        timeout=self.crawler_fetch_url_timeout * 1000
                    )

                    cloudflare_bypass = CloudflareBypass(page)
                    try:
                        # 先尝试模拟人类交互
                        await cloudflare_bypass.simulate_human_interaction()
                        # 然后处理Cloudflare挑战
                        html = await cloudflare_bypass.handle_cloudflare()
                    except Exception as e:
                        logger.warning(f"Cloudflare绕过过程中出错: {str(e)}")
                        # 即使出错也尝试获取页面内容
                        try:
                            html = await page.inner_html("body")
                        except Exception as content_error:
                            logger.error(f"获取页面内容失败: {str(content_error)}")
                            html = None
                    if html:
                        text = await page.inner_text("body")
                        is_high_quality, score = quality_classifier.predict_quality(text)
                        if is_high_quality:
                            logger.info(f"获取到高质量内容 (分数: {score:.2f}): {url}")
                            return html
                        else:
                            logger.warning(f"过滤低质量内容 (分数: {score:.2f}): {url}")
                            return None
                    else:
                        return None
                finally:
                    try:
                        await context.close()
                    except Exception as context_error:
                        logger.warning(f"关闭浏览器上下文失败: {str(context_error)}")
                    try:
                        await browser.close()
                    except Exception as browser_error:
                        logger.warning(f"关闭浏览器失败: {str(browser_error)}")
        except Exception as e:
            logger.error(f"获取页面内容失败: {str(e)}")
            return None

    def parse_html(self, html_content: str) -> Optional[BeautifulSoup]:
        """
        将HTML内容解析为BeautifulSoup对象
        
        Args:
            html_content: HTML内容字符串
            
        Returns:
            Optional[BeautifulSoup]: 解析后的BeautifulSoup对象，解析失败则返回None
        """
        if not html_content:
            return None
            
        try:
            return BeautifulSoup(html_content, 'html.parser')
        except Exception as e:
            logger.error(f"解析HTML内容时出错: {e}")
            return None

    def get_domain(self, url: str) -> str:
        """
        获取URL的域名
        
        Args:
            url: 网址
            
        Returns:
            str: 域名
        """
        try:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except Exception as e:
            logger.error(f"解析域名出错 {url}: {e}")
            return ""

    def html2md(self, html: str) -> str:
        """
        将HTML内容转换为Markdown
        
        Args:
            html: HTML内容字符串
        Returns:
            str: 转换后的Markdown内容
        """
        if not html:
            return ""

        # 定义需要彻底删除的标签（包含内容）
        strip_tags = [
            "script", "style", "img", "a",          # 删除脚本、样式、图片、链接
            "nav", "footer", "header", "aside",     # 删除页眉页脚等非正文区域
            "iframe", "form", "button", "input",    # 删除交互组件
            "svg", "meta", "link"                   # 删除SVG和资源引用
        ]
        
        # 删除标签及其内容（直接彻底清除）
        soup = self.parse_html(html)
        for tag in soup(strip_tags):
            tag.decompose()

        # 定义需要保留文本但删除标签的转换规则
        convert_rules = [
            ("div", lambda tag, _: tag.text),      # 提取div内的文本
            ("span", lambda tag, _: tag.text),      # 提取span内的文本
            ("strong", lambda tag, _: tag.text),    # 去加粗符号
            ("em", lambda tag, _: tag.text),        # 去斜体符号
            ("li", lambda tag, _: tag.text + "\n")  # 列表项转为纯文本+换行
        ]

        return md(
            str(soup), 
            convert=convert_rules,
            heading_style=None,
            strong_em_symbol='',
            bullets='',
            wrap_text=False    
        )

class ContentQualityClassifier:
    """
    使用BERT模型对网页内容进行质量分类
    """
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.max_length = 512
        self.quality_threshold = 0.5
        
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "local_models")
        os.makedirs(cache_dir, exist_ok=True)

        snapshot_dir_cn = os.path.join(
            cache_dir,
            "models--hfl--chinese-roberta-wwm-ext",
            "snapshots",
            os.listdir(f"{cache_dir}/models--hfl--chinese-roberta-wwm-ext/snapshots")[0]
        )
        logger.info(f"尝试从本地加载中文友好分类模型: {snapshot_dir_cn}")
        self.tokenizer_cn = AutoTokenizer.from_pretrained(snapshot_dir_cn)
        self.model_cn = AutoModelForMaskedLM.from_pretrained(snapshot_dir_cn)
        self.model_cn.to(self.device)
        self.model_cn.eval()
        self.classifier_cn = pipeline(
            "zero-shot-classification", 
            model=self.model_cn,
            tokenizer=self.tokenizer_cn, 
            device=self.device,
            max_length=self.max_length,
            truncation=True,
            candidate_labels=["low", "high"]
        )

        snapshot_dir_en = os.path.join(
            cache_dir,
            "models--FacebookAI--xlm-roberta-large",
            "snapshots",
            os.listdir(f"{cache_dir}/models--FacebookAI--xlm-roberta-large/snapshots")[0]
        )
        logger.info(f"尝试从本地加载英文友好分类模型: {snapshot_dir_en}")
        self.tokenizer_en = AutoTokenizer.from_pretrained(snapshot_dir_en)
        self.model_en = AutoModelForMaskedLM.from_pretrained(snapshot_dir_en)
        self.model_en.to(self.device)
        self.model_en.eval()
        self.classifier_en = pipeline(
            "zero-shot-classification", 
            model=self.model_en,
            tokenizer=self.tokenizer_en, 
            device=self.device,
            max_length=self.max_length,
            truncation=True,
            candidate_labels=["low", "high"]
        )
    
    def _preprocess_text(self, text):
        """预处理文本，提取有意义的内容片段"""
        if not text:
            return ""
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', ' ', text)
        # 移除多余空白字符
        text = re.sub(r'\s+', ' ', text)
        # 超过模型能处理的长度，进行截断
        if len(text) > self.max_length:
            text = text[:self.max_length]
        return text
    
    def predict_quality(self, text):
        """
        预测内容质量
        
        Args:
            text: 网页内容文本
            
        Returns:
            tuple: (is_high_quality, score)
        """
        # 首先使用基本规则过滤
        if self._rule_based_filter(text):
            return False, 0.0
        
        try:
            processed_text = self._preprocess_text(text)
            result = self.classifier_cn(processed_text)
            quality_score = result['scores'][result['labels'].index("high")]
            is_high_quality = quality_score >= self.quality_threshold
            logger.info(f"中文质量预测结果: {is_high_quality}, 分数: {quality_score}")
            if not is_high_quality:
                result = self.classifier_en(processed_text)
                quality_score = result['scores'][result['labels'].index("high")]
                is_high_quality = quality_score >= self.quality_threshold
                logger.info(f"英文质量预测结果: {is_high_quality}, 分数: {quality_score}")
            return is_high_quality, quality_score
        except Exception as e:
            logger.error(f"预测内容质量时出错: {str(e)}")
            return True, 0.5
    
    def _rule_based_filter(self, text):
        """基础规则过滤，检测明显的低质量内容"""
        if not text:
            return True
            
        # 文本过短
        if len(text) < 150:
            return True
            
        # 规则1: 检测乱码（非中文/英文/数字/常用标点符号占比过高）
        non_valid_chars = re.findall(r'[^\u4e00-\u9fa5a-zA-Z0-9，。！？、,\.!?]', text)
        if len(non_valid_chars) / max(len(text), 1) > 0.3:  # 非有效字符超过30%
            return True
            
        # 规则2: 重复内容检测
        words = text.split()
        if len(words) > 20 and len(set(words)) / max(len(words), 1) < 0.4:  # 词汇多样性过低
            return True
            
        # 规则3: 检测垃圾内容标志
        keywords = [
            'click here', 'buy now', 'limited offer', 'free download',
            'make money', 'earn cash', '点击这里', '立即购买', '限时优惠',
            "免费领取", "限时优惠", "点击下载", "立即注册", 
            "v信", "加微", "低价出售", "【广告】"
        ]
        lower_text = text.lower()
        if any(keyword in lower_text for keyword in keywords):
            return True

        # 检测反爬验证页面
        captcha_patterns = [
            "detected unusual traffic",
            "systems have detected unusual",
            "IP address:",
            "This page checks",
            "see if it's really you",
            "not a robot",
            "Why did this happen"
        ]
        text_lower = text.lower()
        for pattern in captcha_patterns:
            if pattern.lower() in text_lower:
                logger.info("检测到反爬验证页面，已过滤")
                return True
        
        return False

quality_classifier = ContentQualityClassifier()

class ArxivCrawler(WebCrawler):
    """
    专用于Arxiv论文网站的爬虫
    """
    
    def __init__(self):
        """初始化Arxiv爬虫"""
        super().__init__()
    
    def is_valid_url(self, url: str) -> bool:
        """
        检查URL是否有效且符合arxiv爬取要求
        
        Args:
            url: 要检查的URL
        
        Returns:
            bool: 如果URL有效且应该被爬取则返回True
        """
        # 检查基本有效性
        if not url or not isinstance(url, str):
            return False
        
        # 确保URL是arxiv相关
        if not ('arxiv.org' in url):
            return False
        
        # 专注于论文页面，排除其他arxiv页面如博客、帮助等
        if any(exclude in url for exclude in ['/blog/', '/help/', '/about/', '/login/', '/search/']):
            return False
        
        # 如果URL包含具体论文标识（通常是abs/或html/或pdf/开头的路径）则认为有效
        return '/abs/' in url or '/html/' in url or '/pdf/' in url
    
    def is_arxiv_url(self, url: str) -> bool:
        """
        检查URL是否为ArXiv的URL
        
        Args:
            url: 要检查的URL
            
        Returns:
            bool: 如果是ArXiv URL则返回True
        """
        if not url or not isinstance(url, str):
            return False
            
        return 'arxiv.org' in url or '/arxiv/' in url

    async def parse_sub_url(self, query: str) -> List[str]:
        """
        搜索ArXiv论文
        
        Args:
            query: 搜索关键词
        Returns:
            List[str]: 搜索结果列表
        """
        # 对非英文查询进行处理，增加相关英文关键词，提高搜索质量
        enhanced_query = query
        
        # 如果查询包含中文字符，添加英文关键词增强查询
        if any(u'\u4e00' <= c <= u'\u9fff' for c in query):
            # 将常见的中文医疗AI术语映射到英文
            cn_to_en_terms = {
                "人工智能": "artificial intelligence",
                "医疗": "healthcare medical",
                "诊断": "diagnosis diagnostic",
                "影像": "imaging radiology",
                "机器学习": "machine learning",
                "深度学习": "deep learning",
                "预测": "prediction predictive",
                "预防": "prevention preventive",
                "治疗": "treatment therapy",
                "患者": "patient"
            }
            
            # 尝试添加英文关键词
            english_terms = []
            for cn_term, en_term in cn_to_en_terms.items():
                if cn_term in query:
                    english_terms.append(en_term)
            
            # 构建增强的英文查询
            if english_terms:
                enhanced_query = " ".join(english_terms)
                logger.info(f"将中文查询 '{query}' 增强为英文查询 '{enhanced_query}'")
        
        # 对查询进行URL编码
        encoded_query = quote(enhanced_query)
        search_url = f"https://arxiv.org/search/?query={encoded_query}&searchtype=all"
        
        try:
            logger.info(f"搜索ArXiv论文: {search_url}")
            response = await self.fetch_url_with_proxy_fallback(search_url)
            
            if not response:
                logger.error(f"获取ArXiv搜索结果失败: {search_url}")
                return []
                
            soup = BeautifulSoup(response, 'html.parser')
            paper_links = []
            paper_ids = []

            # 首先尝试新版arXiv页面格式提取论文ID或链接
            for a_tag in soup.select('a'):
                # 尝试找到论文链接
                if a_tag and 'href' in a_tag.attrs:
                    link = a_tag['href']
                    if 'arxiv.org' not in link:
                        link = 'https://arxiv.org' + link
                    if not self.is_valid_url(link):
                        continue
                    paper_links.append(link)
                    
                    # 同时提取论文ID
                    paper_id_match = re.search(r'(\d+\.\d+)', link)
                    if paper_id_match:
                        paper_ids.append(paper_id_match.group(1))
            
            # 如果只有ID没有完整链接，构建链接
            if len(paper_ids) > len(paper_links):
                paper_links = [f"https://arxiv.org/abs/{paper_id}" for paper_id in paper_ids]
            return paper_links
        except Exception as e:
            logger.error(f"搜索ArXiv论文时出错: {e}", exc_info=True)
            return []

    async def fetch_url(self, url: str) -> Optional[str]:
        """
        获取URL内容，带重试机制
        
        Args:
            url: 目标URL
            max_retries: 最大重试次数
            retry_delay: 重试延迟(秒)
            
        Returns:
            Optional[str]: HTML内容
        """
        for attempt in range(1, self.crawler_fetch_url_max_retries + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.headers, timeout=self.crawler_fetch_url_timeout) as response:
                        if response.status == 200:
                            return await response.text()
                        elif response.status == 429:  # 被限流
                            logger.warning(f"请求被限流 (HTTP 429)，等待重试: {url}")
                        else:
                            logger.error(f"HTTP错误 {response.status}: {url}")
                            
                # 只有非成功响应才会执行到这里
                if attempt < self.crawler_fetch_url_max_retries:
                    wait_time = self.crawler_fetch_url_retry_delay * attempt
                    logger.info(f"等待 {wait_time} 秒后进行第 {attempt+1}/{self.crawler_fetch_url_max_retries} 次重试...")
                    await asyncio.sleep(wait_time)
                    
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"获取URL出错 (尝试 {attempt}/{self.crawler_fetch_url_max_retries}): {url}, 错误: {str(e)}")
                if attempt < self.crawler_fetch_url_max_retries:
                    wait_time = self.crawler_fetch_url_retry_delay * attempt
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    await asyncio.sleep(wait_time)
            except Exception as e:
                logger.exception(f"获取URL时发生意外错误: {url}")
                if attempt < self.crawler_fetch_url_max_retries:
                    wait_time = self.crawler_fetch_url_retry_delay * attempt
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    await asyncio.sleep(wait_time)
        
        logger.error(f"在{self.crawler_fetch_url_max_retries}次尝试后仍无法获取URL: {url}")
        return None

class GithubCrawler(WebCrawler):
    """
    专用于GitHub的爬虫
    """
    
    def __init__(self):
        """初始化GitHub爬虫"""
        super().__init__()
        self.github_token = os.getenv("GITHUB_TOKEN")
    
    def is_github_url(self, url: str) -> bool:
        """
        检查URL是否为GitHub的URL
        
        Args:
            url: 要检查的URL
            
        Returns:
            bool: 如果是GitHub URL则返回True
        """
        if not url or not isinstance(url, str):
            return False
            
        return 'github.com' in url or '/github/' in url
            
    async def parse_sub_url(self, query: str) -> List[str]:
        """
        在GitHub上搜索仓库
        
        Args:
            query: 搜索关键词
        Returns:
            List[str]: 搜索结果列表
        """
        logger.info(f"搜索GitHub仓库: {query}")
        
        # GitHub搜索URL
        search_url = f"https://github.com/search?q={quote(query)}"
        
        try:
            html_content = await self.fetch_url_with_proxy_fallback(search_url)
            if not html_content:
                logger.error(f"无法获取GitHub搜索结果: {search_url}")
                return []
                
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 提取搜索结果
            results = []
            articles = soup.select('.repo-list-item')
            
            for article in articles:
                try:
                    link_elem = article.select_one('h3 a')
                    
                    if link_elem:
                        url = link_elem.get('href', '')
                        # 对URL进行完整处理
                        if url and not url.startswith('http'):
                            url = urljoin('https://github.com/', url)
                            
                        results.append(url)
                except Exception as e:
                    logger.error(f"处理GitHub搜索结果项时出错: {str(e)}", exc_info=True)
                    continue
                    
            return results
            
        except Exception as e:
            logger.error(f"搜索GitHub仓库出错: {query}, 错误: {str(e)}", exc_info=True)
            return []

class WeChatOfficialAccountCrawler(WebCrawler):
    """
    专用于微信公众号文章的爬虫
    """
    
    def __init__(self):
        """初始化微信公众号爬虫"""
        super().__init__()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        # 微信文章选择器
        self.selectors = {
            'title': '#activity-name',
            'author': '#js_name',
            'date': '#publish_time',
            'content': '#js_content',
        }
            
    async def parse_sub_url(self, query: str) -> List[str]:
        """
        搜索微信公众号文章
        
        Args:
            query: 搜索查询
        Returns:
            List[str]: 文章URL列表
        """
        logger.info(f"搜索微信公众号文章: {query}")
        
        # 搜狗微信搜索URL
        search_url = f"https://weixin.sogou.com/weixin?type=2&query={quote(query)}"
        
        try:
            html_content = await self.fetch_url_with_proxy_fallback(search_url)
            if not html_content:
                logger.error(f"无法获取微信搜索结果: {search_url}")
                return []
                
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 提取搜索结果
            results = []
            articles = soup.select('.news-box .news-list li')
            
            for article in articles:
                try:
                    link_elem = article.select_one('h3 a')
                    
                    if link_elem:
                        url = link_elem.get('href', '')
                        # 对URL进行完整处理
                        if url and not url.startswith('http'):
                            url = urljoin('https://weixin.sogou.com/', url)
                            
                        results.append(url)
                except Exception as e:
                    logger.error(f"处理微信搜索结果项时出错: {str(e)}", exc_info=True)
                    continue
                    
            return results
            
        except Exception as e:
            logger.error(f"搜索微信公众号文章出错: {query}, 错误: {str(e)}", exc_info=True)
            return []

class CrawlerManager:
    """
    爬虫管理器，管理所有专用爬虫，根据URL选择合适的爬虫
    """
    
    def __init__(self):
        self.config = CrawlerConfig()
        self.arxiv_crawler = ArxivCrawler()
        self.github_crawler = GithubCrawler()
        self.web_crawler = WebCrawler()
        self.wechat_crawler = WeChatOfficialAccountCrawler()
        
    def get_platforms_by_scenario(self, scenario: str) -> List[str]:
        """
        根据场景获取对应的平台列表
        
        Args:
            scenario: 场景名称，如 'general', 'academic', 'news' 等
            
        Returns:
            List[str]: 该场景下应该使用的平台列表
        """
        try:
            if hasattr(self.config, 'db_manager') and self.config.db_manager:
                platforms = self.config.db_manager.get_platforms_by_scenario_name(scenario)
                if platforms:
                    logger.info(f"从数据库获取场景'{scenario}'的平台: {platforms}")
                    return platforms
            return []  
        except Exception as e:
            logger.error(f"获取场景'{scenario}'对应平台时出错: {str(e)}")
            return []

    async def search(self, platform, query, session_id=None):
        """
        根据平台选择合适的爬虫进行搜索
        
        Args:
            platform: 平台名称，如 'arxiv', 'github', 'web_site', 'wechat'
            query: 搜索查询词
            session_id: 会话ID，用于标识搜索任务
            
        Returns:
            List[Dict]: 搜索结果列表
        """
        results = []
        try:
            if platform == 'arxiv':
                # 使用ArxivCrawler搜索
                urls = await self.arxiv_crawler.parse_sub_url(query)
                for url in urls:
                    try:
                        content = await self.arxiv_crawler.crawl_url(url)
                        if content:
                            results.append(content)
                    except Exception as e:
                        continue
            
            elif platform == 'github':
                # 使用GithubCrawler搜索
                urls = await self.github_crawler.parse_sub_url(query)
                for url in urls:
                    try:
                        content = await self.github_crawler.crawl_url(url)
                        if content:
                            results.append(content)
                    except Exception as e:
                        continue
            
            elif platform == 'wechat':
                # 使用WeChatOfficialAccountCrawler搜索
                urls = await self.wechat_crawler.parse_sub_url(query)
                for url in urls:
                    try:
                        content = await self.wechat_crawler.crawl_url(url)
                        if content:
                            results.append(content)
                    except Exception as e:
                        continue
            
            elif platform == 'web_site' or platform == 'web':
                # 使用通用WebCrawler搜索
                urls = await self.web_crawler.parse_sub_url(query)
                for url in urls:
                    try:
                        content = await self.web_crawler.crawl_url(url)
                        if content:
                            results.append(content)
                    except Exception as e:
                        continue
        except Exception as e:
            logger.error(f"在{platform}平台搜索{query}时出错: {str(e)}", exc_info=True)
            
        return results