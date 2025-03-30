import random
import time
import hashlib
import hmac
import uuid
import json
from urllib.parse import urlencode
import requests
import redis
import os
import sys

from typing import List

import logging

from alibabacloud_dysmsapi20170525.client import Client as Dysmsapi20170525Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_dysmsapi20170525 import models as dysmsapi_20170525_models
from alibabacloud_tea_util import models as util_models
from alibabacloud_tea_util.client import Client as UtilClient

logger = logging.getLogger(__name__)

class SmsService:
    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0, **config):
        """
        初始化短信服务
        :param config: 不同服务商需要的配置参数
        """
        config = open_api_models.Config(
            access_key_id=os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID"),
            access_key_secret=os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET"),
            endpoint = f'dysmsapi.aliyuncs.com'
        )
        self.client = Dysmsapi20170525Client(config)
        self.redis = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )

    def generate_code(self, length=6):
        """生成指定位数的数字验证码"""
        return ''.join(random.choices('0123456789', k=length))

    def send_sms(self, phone_number):
        """
        发送短信验证码（统一入口）
        :param phone_number: 目标手机号
        :return: 发送结果 (success, message)
        """
        code = self.generate_code()
        self.redis.setex(f'sms:{phone_number}', 300, code)
        send_sms_request = dysmsapi_20170525_models.SendSmsRequest()
        send_sms_request.phone_numbers = phone_number
        send_sms_request.sign_name = os.getenv("SIGN_NAME")
        send_sms_request.template_code = os.getenv("TEMPLATE_CODE")
        send_sms_request.template_param = json.dumps({"code": code})
        runtime = util_models.RuntimeOptions()
        try:
            result = self.client.send_sms_with_options(send_sms_request, runtime)
            logger.info(f"发送短信结果: {result}")
            if result.body.code == 'OK':
                return True
            else:
                logger.error(f"发送短信失败: {result.body.message}")
                return False
        except Exception as error:
            logger.error(f"发送短信失败: {str(error)}")
            return False

    def verify_code(self, phone_number, input_code):
        """
        验证短信验证码
        :param phone_number: 手机号
        :param input_code: 用户输入的验证码
        :return: 验证结果 (success, message)
        """
        stored_code = self.redis.get(f'sms:{phone_number}')
        if not stored_code:
            logger.error("验证码已过期或未发送")
            return False
        if stored_code != input_code:
            logger.error("验证码不正确")
            return False
        self.redis.delete(f'sms:{phone_number}')
        return True

sms_service = SmsService()

if __name__ == "__main__":
    phone = '15392482014'
    success = sms_service.send_sms(phone)
    if success:
        print(f"发送成功到{phone}")
    else:
        print(f"发送失败{phone}")
    user_input = input("请输入收到的验证码: ")
    verify_result, verify_msg = sms_service.verify_code(phone, user_input)
    print(f"验证结果: {verify_msg}")