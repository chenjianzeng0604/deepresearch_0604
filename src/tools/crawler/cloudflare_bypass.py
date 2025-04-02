import asyncio
import random
import os
import base64
import aiohttp
from playwright.async_api import Page
from typing import Optional, Tuple
import requests
import logging

logger = logging.getLogger(__name__)

class CloudflareBypass:
    def __init__(self, page: Page):
        self.page = page
        self.captcha_api_key = os.getenv("2CAPTCHA_API_KEY")
        self.max_retries = 2
        self.cloudflare_bypass_wait_for_timeout = int(os.getenv("CLOUDFLARE_BYPASS_WAIT_FOR_TIMEOUT", 1000))
        self.crawler_fetch_url_timeout = int(os.getenv("CRAWLER_FETCH_URL_TIMEOUT", 10))

    async def handle_cloudflare(self) -> Optional[str]:
        """
        处理Cloudflare验证流程
        返回: 最终HTML内容
        """
        for attempt in range(self.max_retries):
            try:
                if not await self._detect_challenge():
                    return await self.page.inner_html("body")

                challenge_type = await self._get_challenge_type()
                if challenge_type == "turnstile":
                    success = await self._solve_turnstile()
                elif challenge_type == "image":
                    success = await self._solve_image_captcha()
                else:
                    success = await self._solve_auto_verify()

                if success:
                    return await self.page.inner_html("body")

                await self._rotate_proxy()
            except Exception as e:
                logger.warning(f"处理Cloudflare验证流程时出错 (尝试 {attempt+1}/{self.max_retries}): {str(e)}")

        try: 
            return await self.page.inner_html("body")
        except Exception as final_error:
            logger.warning(f"最终获取页面内容失败: {str(final_error)}")
            return None

    async def _detect_challenge(self) -> bool:
        """检测是否存在验证挑战"""
        try:
            return await self.page.query_selector("text=Checking if the site connection is secure") is not None
        except Exception as e:
            logger.warning(f"检测验证挑战时出错: {str(e)}")
            # 如果出错，假设存在挑战
            return True

    async def _get_challenge_type(self) -> str:
        """识别挑战类型"""
        try:
            if await self.page.query_selector("iframe[src*='challenges.cloudflare.com']"):
                return "turnstile"
            elif await self.page.query_selector(".challenge-image"):
                return "image"
            return "auto"
        except Exception as e:
            logger.warning(f"识别挑战类型时出错: {str(e)}")
            # 如果出错，默认使用自动验证
            return "auto"

    async def _solve_turnstile(self) -> bool:
        """处理Turnstile验证"""
        frame = await self._get_challenge_frame()
        if not frame:
            return False

        sitekey = await frame.evaluate("""
            document.querySelector('[data-sitekey]')?.dataset.sitekey
        """)
        if not sitekey:
            return False

        token = await self._get_turnstile_token(sitekey)
        if not token:
            return False

        await frame.evaluate(f"""
            document.querySelector('input[name=cf-turnstile-response]').value = '{token}';
            document.querySelector('form').submit();
        """)
        return True

    async def _solve_image_captcha(self) -> bool:
        """处理图像验证码"""
        img_element = await self.page.query_selector(".challenge-image")
        if not img_element:
            return False

        # 截图并解决验证码
        img_data = await img_element.screenshot()
        solution = await self._solve_image(img_data)
        if not solution:
            return False

        # 输入答案并提交
        await self.page.fill("input[name=cf_captcha_answer]", solution)
        await self.page.click("button[type=submit]")
        return True

    async def _solve_auto_verify(self) -> bool:
        """处理自动验证流程"""
        await self.simulate_human_interaction()
        return not await self._detect_challenge()

    async def _get_challenge_frame(self):
        """获取挑战iframe"""
        try:
            frame_element = await self.page.wait_for_selector(
                "iframe[src*='challenges.cloudflare.com']",
                timeout=15000
            )
            return await frame_element.content_frame()
        except:
            return None

    async def _get_turnstile_token(self, sitekey: str) -> Optional[str]:
        """通过2Captcha获取Turnstile token"""
        params = {
            "key": self.captcha_api_key,
            "method": "turnstile",
            "sitekey": sitekey,
            "pageurl": self.page.url
        }

        async with aiohttp.ClientSession() as session:
            try:
                # 提交验证请求
                async with session.post(
                    "https://2captcha.com/in.php",
                    data=params,
                    timeout=10
                ) as resp:
                    result = await resp.text()
                    if "OK|" not in result:
                        return None
                    task_id = result.split("|")[1]

                start_time = asyncio.get_event_loop().time()
                while (asyncio.get_event_loop().time() - start_time) < 120:
                    await asyncio.sleep(5)
                    async with session.get(
                        f"https://2captcha.com/res.php?key={self.captcha_api_key}"
                        f"&action=get&id={task_id}"
                    ) as resp:
                        result = await resp.text()
                        if "OK|" in result:
                            return result.split("|")[1]
                        elif result == "CAPCHA_NOT_READY":
                            continue
                return None

            except (aiohttp.ClientError, asyncio.TimeoutError):
                return None

    async def _solve_image(self, image_data: bytes) -> Optional[str]:
        """解决图像验证码"""
        encoded_image = base64.b64encode(image_data).decode()
        params = {
            "key": self.captcha_api_key,
            "method": "base64",
            "body": encoded_image,
            "json": 1
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    "https://2captcha.com/in.php",
                    data=params,
                    timeout=10
                ) as resp:
                    result = await resp.json()
                    if result.get("status") != 1:
                        return None
                    task_id = result["request"]

                # 等待结果
                start_time = asyncio.get_event_loop().time()
                while (asyncio.get_event_loop().time() - start_time) < 120:
                    await asyncio.sleep(5)
                    async with session.get(
                        f"https://2captcha.com/res.php?key={self.captcha_api_key}"
                        f"&action=get&id={task_id}&json=1"
                    ) as resp:
                        result = await resp.json()
                        if result.get("status") == 1:
                            return result["request"]
                return None

            except (aiohttp.ClientError, asyncio.TimeoutError):
                return None

    async def simulate_human_interaction(self):
        """模拟人类交互行为"""
        await self._random_mouse_movement()
        await self._random_scroll()
        if random.random() < 0.3:
            await self._random_click()
        
        for attempt in range(self.max_retries):
            try:
                if not await self.page.is_visible("body"):
                    logger.warning("页面可能已导航，等待页面加载")
                    await self.page.wait_for_load_state("domcontentloaded", timeout=self.crawler_fetch_url_timeout * 1000)
                
                await self.page.evaluate("generateMouseMove()")
                await self.page.wait_for_timeout(self.cloudflare_bypass_wait_for_timeout)
                break
            except Exception as e:
                logger.warning(f"模拟人类交互时出错 (尝试 {attempt+1}/{self.max_retries}): {str(e)}")

    async def _random_mouse_movement(self):
        """生成随机鼠标轨迹"""
        try:
            for _ in range(random.randint(3, 5)):
                x = random.randint(0, 800)
                y = random.randint(0, 600)
                await self.page.mouse.move(x, y)
                await self.page.wait_for_timeout(random.randint(10, 50))
        except Exception as e:
            logger.warning(f"随机鼠标移动时出错: {str(e)}")

    async def _random_scroll(self):
        """随机滚动页面"""
        try:
            scrolls = random.randint(1, 3)
            for _ in range(scrolls):
                await self.page.mouse.wheel(
                    0, 
                    random.randint(300, 800) * random.choice([1, -1])
                )
                await self.page.wait_for_timeout(random.randint(100, 200))
        except Exception as e:
            logger.warning(f"随机滚动页面时出错: {str(e)}")
            # 继续执行，不抛出异常

    async def _random_click(self):
        """在随机位置点击"""
        try:
            x = random.randint(0, 800)
            y = random.randint(0, 600)
            await self.page.mouse.click(x, y, delay=random.randint(10, 50))
        except Exception as e:
            logger.warning(f"随机点击时出错: {str(e)}")
            # 继续执行，不抛出异常

    async def _rotate_proxy(self):
        """切换代理"""
        new_proxy = await self._get_proxy()
        if not new_proxy:
            return
        await self.page.context.set_extra_http_headers({
            "X-Proxy": new_proxy
        })
        logger.info(f"切换代理至: {new_proxy}")
    
    async def _get_proxy(self):
        api = "https://tps.kdlapi.com/api/gettpspro"
        params = {
            "secret_id": "of9bivpnespnxn2p0rd5",
            "signature": "ysh000yyp4y2plir0besrnzruvv7wv2j",
            "num": 1
        }
        response = requests.get(api, params=params)
        return response.text