import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class BaseDistributor(ABC):
    """基础分发器，定义了分发内容到不同平台的通用接口"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get("enabled", False)
        self.name = self.__class__.__name__
    
    @abstractmethod
    async def distribute(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        将内容分发到指定平台
        
        Args:
            content: 需要分发的内容，包含标题、正文、图片等
            
        Returns:
            Dict[str, Any]: 分发结果，包含成功状态和平台特定的返回信息
        """
        pass
    
    async def validate_config(self) -> bool:
        """
        验证配置是否有效
        
        Returns:
            bool: 配置是否有效
        """
        # 基本验证：配置是否启用
        return self.enabled

    async def format_content(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据平台要求格式化内容
        
        Args:
            content: 原始内容
            
        Returns:
            Dict[str, Any]: 格式化后的内容
        """
        # 基础实现：复制原始内容
        return content.copy()
    
    async def test_connection(self) -> bool:
        """
        测试与平台的连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 默认实现：验证配置
            return await self.validate_config()
        except Exception as e:
            logger.error(f"{self.name} 测试连接失败: {e}")
            return False

class DisabledDistributor(BaseDistributor):
    """已禁用的分发器，用于表示某个分发器已被禁用"""
    
    def __init__(self, dist_type: str):
        super().__init__({"enabled": False})
        self.dist_type = dist_type
        self.name = f"禁用的{dist_type}分发器"
        
    async def distribute(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        不执行实际分发，返回禁用状态
        
        Args:
            content: 需要分发的内容
            
        Returns:
            Dict[str, Any]: 分发结果，表示已禁用
        """
        logger.info(f"{self.name}已禁用，跳过分发")
        return {
            "success": False,
            "message": f"{self.name}已禁用",
            "platform": self.dist_type,
            "disabled": True
        }
    
    async def validate_config(self) -> bool:
        """始终返回False，表示配置无效"""
        return False

class DistributionManager:
    """分发管理器，协调多个分发器的工作"""
    
    def __init__(self, distributors: Dict[str, BaseDistributor]):
        self.distributors = distributors
        self.enabled_distributors = {
            name: dist for name, dist in distributors.items() 
            if dist.enabled
        }
        
    def get_enabled_platforms(self) -> List[str]:
        """
        获取所有已启用的分发平台
        
        Returns:
            List[str]: 已启用的分发平台列表
        """
        return list(self.enabled_distributors.keys())
        
    async def distribute_all(self, content: str) -> Dict[str, Any]:
        """
        将内容分发到所有启用的平台
        
        Args:
            content: 需要分发的内容
            
        Returns:
            Dict[str, Any]: 各平台的分发结果
        """
        results = {}
        tasks = []
        
        # 为每个启用的分发器创建任务
        for name, distributor in self.enabled_distributors.items():
            task = asyncio.create_task(self._distribute_to_platform(name, distributor, content))
            tasks.append(task)
        
        # 等待所有任务完成
        if tasks:
            await asyncio.gather(*tasks)
            for task in tasks:
                platform_name, result = task.result()
                results[platform_name] = result
        
        return results
    
    async def distribute(self, content: str, platforms: List[str] = None) -> Dict[str, Any]:
        """
        将内容分发到指定平台列表
        
        Args:
            content: 需要分发的内容
            platforms: 指定的平台列表，如果为None则分发到所有启用的平台
            
        Returns:
            Dict[str, Any]: 各平台的分发结果
        """
        results = {}
        tasks = []
        
        # 如果没有指定平台，则使用所有启用的平台
        if platforms is None:
            platforms = self.get_enabled_platforms()
        
        # 过滤出已启用且在指定平台列表中的分发器
        target_distributors = {
            name: dist for name, dist in self.distributors.items() 
            if name in platforms and dist.enabled
        }
        
        # 为每个目标分发器创建任务
        for name, distributor in target_distributors.items():
            task = asyncio.create_task(self._distribute_to_platform(name, distributor, content))
            tasks.append(task)
        
        # 等待所有任务完成
        if tasks:
            await asyncio.gather(*tasks)
            for task in tasks:
                platform_name, result = task.result()
                results[platform_name] = result
        
        return results
    
    async def _distribute_to_platform(self, name: str, distributor: BaseDistributor, content: Dict[str, Any]) -> tuple:
        """
        分发内容到特定平台
        
        Args:
            name: 平台名称
            distributor: 分发器实例
            content: 需要分发的内容
            
        Returns:
            tuple: (平台名称, 分发结果)
        """
        try:
            logger.info(f"开始分发内容到 {name}...")
            formatted_content = await distributor.format_content(content)
            result = await distributor.distribute(formatted_content)
            logger.info(f"分发到 {name} 完成")
            return name, result
        except Exception as e:
            logger.error(f"分发到 {name} 失败: {e}", exc_info=True)
            return name, {"status": "error", "message": str(e)}
    
    async def test_all_connections(self) -> Dict[str, bool]:
        """
        测试所有分发器的连接
        
        Returns:
            Dict[str, bool]: 各平台的连接测试结果
        """
        results = {}
        tasks = []
        
        # 为每个分发器创建测试任务
        for name, distributor in self.distributors.items():
            task = asyncio.create_task(self._test_connection(name, distributor))
            tasks.append(task)
        
        # 等待所有测试完成
        if tasks:
            await asyncio.gather(*tasks)
            for task in tasks:
                platform_name, result = task.result()
                results[platform_name] = result
        
        return results
    
    async def _test_connection(self, name: str, distributor: BaseDistributor) -> tuple:
        """
        测试与特定平台的连接
        
        Args:
            name: 平台名称
            distributor: 分发器实例
            
        Returns:
            tuple: (平台名称, 测试结果)
        """
        try:
            result = await distributor.test_connection()
            return name, result
        except Exception as e:
            logger.error(f"测试 {name} 连接失败: {e}")
            return name, False
