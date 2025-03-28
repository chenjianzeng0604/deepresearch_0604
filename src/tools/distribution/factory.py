import logging
from typing import Dict, Any, List

from src.distribution.base import BaseDistributor, DistributionManager, DisabledDistributor
from src.distribution.wechat import WechatOfficialAccountDistributor

logger = logging.getLogger(__name__)

def create_distributor(dist_type: str, config: Any) -> BaseDistributor:
    """
    创建分发器
    
    Args:
        dist_type: 分发器类型
        config: 分发器配置
        
    Returns:
        BaseDistributor: 分发器实例
    """
    try:
        # 获取启用状态
        enabled = config.enabled if hasattr(config, "enabled") else False
        
        if not enabled:
            logger.info(f"{dist_type}分发器已禁用，跳过创建")
            return DisabledDistributor(dist_type)
        
        # 根据类型创建不同的分发器
        return WechatOfficialAccountDistributor(
            enabled=enabled,
            api_url=config.api_url,
            app_id=config.app_id,
            app_secret=config.app_secret
        )
    except Exception as e:
        logger.error(f"创建{dist_type}分发器失败: {e}")
        return DisabledDistributor(dist_type)

def create_distribution_manager(config: Dict[str, Any]) -> DistributionManager:
    """
    创建分发管理器
    
    Args:
        config: 分发配置
        
    Returns:
        DistributionManager: 分发管理器实例
    """
    distributors = {}
    
    # 遍历配置中的分发器
    platforms = {
        "wechat_official_account": config.wechat_official_account
    }
    
    for dist_type, dist_config in platforms.items():
        if dist_config is None:
            continue
        try:
            # 创建分发器
            distributor = create_distributor(dist_type, dist_config)
            distributors[dist_type] = distributor
            enabled_status = "启用" if distributor.enabled else "禁用"
            logger.info(f"已创建{dist_type}分发器 ({enabled_status})")
        except Exception as e:
            logger.error(f"创建{dist_type}分发器失败: {e}")
    
    # 创建分发管理器
    manager = DistributionManager(distributors)
    logger.info(f"分发管理器已创建，共有{len(distributors)}个分发器，{len(manager.enabled_distributors)}个已启用")
    
    return manager
