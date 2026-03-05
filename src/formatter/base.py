from abc import ABC, abstractmethod
from typing import Optional

class BaseFormatter(ABC):
    @classmethod
    def check_prereq(cls) -> bool:
        return True

    @abstractmethod
    def format_code(self, code: str, repair_strategy: str, info:dict, **kwargs) -> Optional[str]:
        pass
        
    @abstractmethod
    def unformat_code(self, code: str, repair_strategy: str, info: dict, **kwargs) -> Optional[str]:
        pass