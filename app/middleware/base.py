"""
中间件基类
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseMiddleware(ABC):
    """中间件基类"""

    @abstractmethod
    async def process(self, state: Dict[str, Any], action: Any) -> Dict[str, Any]:
        """
        处理中间件逻辑

        Args:
            state: 当前状态
            action: 当前操作

        Returns:
            处理后的状态
        """
        pass

    @abstractmethod
    def should_process(self, state: Dict[str, Any], action: Any) -> bool:
        """
        判断是否需要处理

        Args:
            state: 当前状态
            action: 当前操作

        Returns:
            是否需要处理
        """
        pass
