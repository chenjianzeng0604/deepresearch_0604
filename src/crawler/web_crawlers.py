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

import pdfplumber
from pdfminer.layout import LAParams
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from aiohttp import ClientSession
from src.vectordb.milvus_dao import MilvusDao
import uuid
from playwright.async_api import async_playwright
from src.crawler.cloudflare_bypass import CloudflareBypass
from src.utils.prompt_templates import PromptTemplates
from src.vectordb.schema_manager import MilvusSchemaManager
from src.models.config import AppConfig
from src.utils.llm_client import LLMClient
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class WebCrawler:
    """
    常用网站爬虫，支持主流技术媒体
    """
    
    def __init__(self):
        self.config = AppConfig.from_env()
        self.milvus_dao = MilvusDao(os.getenv("DEEPRESEARCH_COLLECTION"))
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
                     '.mp3', '.mp4', '.avi', '.mov', '.flv', '.wmv')
        if any(parsed.path.lower().endswith(ext) for ext in static_ext):
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
    
    async def extract_pdf(self, url: str) -> Dict[str, Any]:
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
                                return {'content': '\n\n'.join(text_content)}
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
                    links.append(absolute_url)
        except Exception as e:
            logger.error(f"提取链接出错: {base_url}, 错误: {str(e)}")
        return links

    async def parse_sub_url(self, search_url: str) -> List[str]:
        try:
            html_content = await self.fetch_url(search_url)
            if not html_content:
                logger.error(f"主URL获取内容为空: {search_url}")
                return []
            return await self.extract_links(html_content, search_url)
        except Exception as e:
            logger.error(f"parse_sub_url出错: {search_url}, 错误: {str(e)}")
            return []
    
    async def fetch_article_and_save2milvus(self, query: str, links: List[str]) -> List[str]:

        url_list_str = ", ".join([f"'{url}'" for url in links])
        filter_expr = f"url in [{url_list_str}]"

        res = self.milvus_dao._query(
            collection_name=self.milvus_dao.collection_name,
            filter=filter_expr,
            output_fields=["url"],
        )

        if res:
            existing_urls = set(r["url"] for r in res) if res else set()
            links = [link for link in links if link not in existing_urls]

        rows = 0
        sem = asyncio.Semaphore(self.crawler_fetch_article_with_semaphore)
        async def fetch_article_with_semaphore(link):
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
        
        tasks = [fetch_article_with_semaphore(link) for link in links[:self.crawler_max_links_result]]

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"获取文章信息时发生错误: {str(result)}")
                    continue
                    
                if len(result['content'].strip()) > 0:
                    schema, index_params = MilvusSchemaManager.get_schema_by_collection_name(self.milvus_dao.collection_name)
                    contents = self.cut_string_by_length(result['content'], self.article_trunc_word_count)
                    for content in contents:
                        content_embs = self.milvus_dao._generate_embeddings([content])
                        data = [{
                            "id": str(uuid.uuid4()),
                            "url": result['url'],
                            "content": content,
                            "content_emb": content_embs[0],
                            "create_time": int(datetime.now(timezone.utc).timestamp() * 1000)
                        }]
                        self.milvus_dao._store_in_milvus(self.milvus_dao.collection_name, schema, index_params, data)
                        rows += 1
        
            logger.info(f"成功写入{rows}行数据")
            return results
        except Exception as e:
            logger.error(f"获取文章信息时发生错误: {str(e)}")
            return []

    def cut_string_by_length(self, s, length):
        """
        将字符串按固定长度切割成数组

        :param s: 需要切割的字符串
        :param length: 每个子字符串的固定长度
        :return: 切割后的子字符串数组
        """
        return [s[i:i+length] for i in range(0, len(s), length)]


    async def _generate_summary(self, query: str, content: str) -> str:
        if not content or len(content.strip()) == 0:
            return ""
        try:
            summary_analysis_prompt = PromptTemplates.format_summary_analysis_prompt(query, content)
            summary = await self.llm_client.generate(summary_analysis_prompt)
            logger.info(f"生成摘要: {summary}")
            return summary
        except Exception as e:
            logger.error(f"生成摘要时出错: {str(e)}", exc_info=True)
            return ""
    
    def is_pdf_url(self, url: str) -> bool:
        return '/pdf/' in url
    
    async def fetch_url_md(self, url: str) -> Optional[str]:
        """
        获取URL内容
        
        Args:
            url: 要获取的URL
            
        Returns:
            Optional[str]: 成功时返回Markdown内容，失败时返回None
        """
        return self.html2md(await self.fetch_url(url))

    def getReferer(self, url: str) -> str:
        """
        获取URL的Referer
        
        Args:
            url: URL
            
        Returns:
            str: Referer
        """
        parsed = urlparse(url)
        parsed = parsed._replace(
            query='',
            fragment='',
            path=''
        )
        return urlunparse(parsed)

    async def fetch_url(self, url: str) -> Optional[str]:
        try:
            content = await self.fetch_url(url, useProxy=False)    
        except Exception as e:
            logger.error(f"Failed to fetch URL {url} without proxy: {str(e)}")
            content = None
        if content and len(content.strip()) > 0:
            return content
        try:
            return await self.fetch_url(url, useProxy=True)    
        except Exception as e:
            logger.error(f"Failed to fetch URL {url} with proxy: {str(e)}")
            return None
    
    async def fetch_url(self, url: str, useProxy: bool = False) -> Optional[str]:
        async with async_playwright() as p:
            if useProxy:
                logger.info(f"Fetching URL {url} with proxy")
                browser = await p.chromium.launch(
                    channel="chrome",
                    headless=True,
                    proxy=self.proxies,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        f"--user-agent={UserAgent().random}",
                        "--use-fake-ui-for-media-stream",
                        "--use-fake-device-for-media-stream"
                    ],
                    env={"SSLKEYLOGFILE": "/dev/null"}
                )
            else:
                logger.info(f"Fetching URL {url} without proxy")
                browser = await p.chromium.launch(
                    channel="chrome",
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        f"--user-agent={UserAgent().random}",
                        "--use-fake-ui-for-media-stream",
                        "--use-fake-device-for-media-stream"
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
                    if route.request.resource_type in {"image", "stylesheet", "font"} 
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
                    return await cloudflare_bypass.handle_cloudflare()
                except Exception as e:
                    logger.warning(f"Cloudflare绕过过程中出错: {str(e)}")
                    # 即使出错也尝试获取页面内容
                    try:
                        return await page.content()
                    except Exception as content_error:
                        logger.error(f"获取页面内容失败: {str(content_error)}")
                        return None
            finally:
                try:
                    await context.close()
                except Exception as context_error:
                    logger.error(f"关闭浏览器上下文失败: {str(context_error)}")
                try:
                    await browser.close()
                except Exception as browser_error:
                    logger.error(f"关闭浏览器失败: {str(browser_error)}")

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