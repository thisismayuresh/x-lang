"""
HashMap implementation for X Language
"""
from typing import Any


class HashMapClass:
    """X language HashMap class implementation"""
    
    def __init__(self, capacity: int = 16):
        self.data = {}
        self.capacity = capacity
    
    def set(self, key: Any, value: Any) -> None:
        """Set a key-value pair"""
        self.data[str(key)] = value
    
    def get(self, key: Any) -> Any:
        """Get value by key"""
        return self.data.get(str(key))
    
    def has(self, key: Any) -> bool:
        """Check if key exists"""
        return str(key) in self.data
    
    def remove(self, key: Any) -> Any:
        """Remove and return value by key"""
        return self.data.pop(str(key), None)
    
    def size(self) -> int:
        """Return number of entries"""
        return len(self.data)
    
    def isEmpty(self) -> bool:
        """Check if map is empty"""
        return len(self.data) == 0
    
    def clear(self) -> None:
        """Remove all entries"""
        self.data.clear()
    
    def keys(self) -> list[str]:
        """Return all keys"""
        return list(self.data.keys())
    
    def values(self) -> list[Any]:
        """Return all values"""
        return list(self.data.values())
    
    def entries(self) -> list[list[Any]]:
        """Return all [key, value] pairs"""
        return [[k, v] for k, v in self.data.items()]
    
    def getOrDefault(self, key: Any, default: Any) -> Any:
        """Get value or default if not found"""
        return self.data.get(str(key), default)
    
    def merge(self, *others: dict) -> dict:
        """Merge with other maps"""
        result = dict(self.data)
        for other in others:
            if isinstance(other, HashMapClass):
                result.update(other.data)
            elif isinstance(other, dict):
                result.update(other)
        return result
    
    def putAll(self, other: dict) -> None:
        """Copy all entries from another map"""
        if isinstance(other, HashMapClass):
            self.data.update(other.data)
        elif isinstance(other, dict):
            self.data.update(other)
