import logging
import json
import aiohttp
from typing import Dict, Any, Optional

from src.distribution.base import BaseDistributor
from datetime import datetime
import aiofiles
from aiohttp import FormData
import markdown

logger = logging.getLogger(__name__)

class WechatOfficialAccountDistributor(BaseDistributor):
    """微信公众号分发器，用于发布科技分析报告到微信公众号"""
    
    def __init__(self, enabled: bool = False, api_url: str = "", app_id: str = "", 
                 app_secret: str = ""):
        super().__init__({"enabled": enabled})
        self.api_url = api_url
        self.app_id = app_id
        self.app_secret = app_secret
    
    async def validate_config(self) -> bool:
        """验证微信公众号配置是否有效"""
        if not self.enabled:
            return False
        
        return all([
            self.api_url,
            self.app_id,
            self.app_secret
        ])
    
    async def format_content(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """格式化内容为微信公众号文章格式"""
        title = content.get("title", "深度研究报告")
        body = markdown.markdown(
            content.get("content", ""),
            extensions=[
                'fenced_code',  # 代码块
                'tables',       # 表格
                'nl2br'         # 换行转 <br>
            ],
            safe_mode=True
        )
        
        thumb_media_id = await self._upload_image(content.get("cover_image", ""))
        
        formatted = {
            "title": title,
            "thumb_media_id": thumb_media_id,
            "content": body,
            "need_open_comment": 1,
            "only_fans_can_comment": 0
        }
        
        return formatted
    
    async def distribute(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """分发内容到微信公众号"""
        if not await self.validate_config():
            raise ValueError("微信公众号分发器配置无效")
        
        try:
            # 获取访问令牌
            access_token = await self._get_access_token()
            
            # 上传图文消息
            articles = {
                "articles": [content]
            }

            headers = {
                "Content-Type": "application/json; charset=utf-8"  # 明确指定编码
            }

            json_data = json.dumps(articles, ensure_ascii=False)
            
            upload_url = f"{self.api_url}/cgi-bin/draft/add?access_token={access_token}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(upload_url, data=json_data.encode('utf-8'), headers=headers) as response:
                    result = await response.text()
                    result = json.loads(result)
                    if "media_id" in result:
                        media_id = result["media_id"]
                        publish_url = f"{self.api_url}/cgi-bin/freepublish/submit?access_token={access_token}"
                        publish_data = {'media_id': media_id}
                        async with session.post(publish_url, json=publish_data, headers=headers) as response:
                            result = await response.text()
                            result = json.loads(result)
                            if "publish_id" in result:
                                success_msg =  f"发布到微信公众号成功，publish_id: {result['publish_id']}"
                                logger.info(success_msg)
                                # 群发：send_url = f"{self.api_url}/cgi-bin/message/mass/sendall?access_token={access_token}"
                                # send_data = {
                                #     "filter": {
                                #         "is_to_all": True
                                #     },
                                #     "mpnews": {
                                #         "media_id": media_id
                                #     },
                                #     "msgtype": "mpnews",
                                #     "send_ignore_reprint": 0
                                # }
                                # 预览：send_url = f"{self.api_url}/cgi-bin/message/mass/preview?access_token={access_token}"
                                # send_data = {
                                #     "touser":"OPENID", 
                                #     "mpnews":{              
                                #         "media_id": media_id               
                                #     },
                                #     "msgtype":"mpnews" 
                                # }
                                # async with session.post(send_url, json=send_data) as send_response:
                                #     send_result = await send_response.text()
                                #     send_result = json.loads(send_result)
                                #     if send_result.get("errcode") == 0:
                                #         success_msg = f"群发成功，msg_id: {send_result.get('msg_id')}，msg_data_id: {send_result.get('msg_data_id')}"
                                #         logger.info(success_msg)
                                #         return {
                                #             "platform": "wechat_official_account",
                                #             "status": "success",
                                #             "message": success_msg
                                #         }
                                #     else:
                                #         error_msg = f"群发失败: {send_result.get('errmsg') or '未知错误'}"
                                #         logger.error(error_msg)
                                #         return {
                                #             "platform": "wechat_official_account",
                                #             "status": "error",
                                #             "message": error_msg
                                #         }
                                success_msg = f"发布到微信公众号成功，publish_id: {result['publish_id']}"
                                logger.info(success_msg)
                                return {
                                    "platform": "wechat_official_account",
                                    "status": "success",
                                    "message": success_msg
                                }
                            else:
                                error_msg = f"发布到微信公众号失败: {result.get('errmsg') or '未知错误'}"
                                logger.error(error_msg)
                                return {
                                    "platform": "wechat_official_account",
                                    "status": "error",
                                    "message": error_msg
                                }
                    else:
                        error_msg = f"上传图文消息失败: {result.get('errmsg')}"
                        logger.error(error_msg)
                        return {
                            "platform": "wechat_official_account",
                            "status": "error",
                            "message": error_msg
                        }
        
        except Exception as e:
            logger.error(f"微信公众号发布失败: {e}", exc_info=True)
            return {
                "platform": "wechat_official_account",
                "status": "error",
                "message": str(e)
            }
    
    async def _get_access_token(self) -> str:
        """获取微信API访问令牌"""
        token_url = f"{self.api_url}/cgi-bin/token?grant_type=client_credential&appid={self.app_id}&secret={self.app_secret}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(token_url) as response:
                result = await response.json()
                if "access_token" in result:
                    return result["access_token"]
                else:
                    error_msg = f"获取微信访问令牌失败: {result.get('errmsg')}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
    
    async def _upload_image(self, image_path: str) -> str:
        """上传图片到微信服务器获取media_id"""
        if not image_path:
            # 如果没有图片路径，返回空media_id
            return ""
        
        try:
            # 获取访问令牌
            access_token = await self._get_access_token()
            
            # 上传图片
            upload_url = f"{self.api_url}/cgi-bin/material/add_material?access_token={access_token}&type=image"
           

            async with aiofiles.open(image_path, 'rb') as f:
                file_content = await f.read()
                
                # 正确构造 FormData
                data = FormData()
                data.add_field(
                    'media',
                    file_content,
                    filename='image.png',  # 文件名需带扩展名
                    content_type='image/png'  # 根据实际图片类型修改
                )
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(upload_url, data=data) as response:
                        result = await response.text()
                        result = json.loads(result)
                        if "media_id" in result:
                            return result["media_id"]
                        else:
                            errmsg = result.get('errmsg', '未知错误')
                            logger.error(f"上传图片失败: {errmsg}")
                            return ""
        except Exception as e:
            logger.error(f"上传图片失败: {e}")
            return ""
    
    async def test_connection(self) -> bool:
        """测试与微信公众号API的连接"""
        try:
            if not await self.validate_config():
                return False
            
            # 尝试获取访问令牌作为连接测试
            await self._get_access_token()
            return True
        except Exception as e:
            logger.error(f"微信公众号连接测试失败: {e}")
            return False
