import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def str2Json(response: str) -> Dict[str, Any]:
    """
    解析JSON格式字符串
    
    Args:
        response: JSON格式字符串
        
    Returns:
        Dict[str, Any]: 解析后的JSON数据
    """
    try:
        try:
            return json.loads(response.strip())
        except:
            logger.warning(f"解析JSON字符串时出错，原始响应: {response}")
            pass

        # 尝试从响应中提取JSON部分
        import re
        json_match = re.search(r'```json\n(.*?)\n```', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        
        # 尝试找到第一个{和最后一个}之间的内容
        json_match = re.search(r'({.*})', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
    
        return None
    except Exception as e:
        logger.error(f"解析JSON字符串时出错，原始响应: {response}")
        return None
