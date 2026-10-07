"""
LinkedList implementation for X Language
"""
from typing import Any


class LinkedListClass:
    """X language LinkedList class implementation"""
    
    def __init__(self, initial_array: list = None):
        self.data = list(initial_array) if initial_array else []
    
    def add(self, value: Any) -> None:
        """Add to end"""
        self.data.append(value)
    
    def addFirst(self, value: Any) -> None:
        """Add to beginning"""
        self.data.insert(0, value)
    
    def addLast(self, value: Any) -> None:
        """Add to end"""
        self.data.append(value)
    
    def remove(self, value: Any) -> bool:
        """Remove first occurrence"""
        try:
            self.data.remove(value)
            return True
        except ValueError:
            return False
    
    def removeFirst(self) -> Any:
        """Remove and return first element"""
        if not self.data:
            raise Exception("LinkedList.removeFirst: list is empty")
        return self.data.pop(0)
    
    def removeLast(self) -> Any:
        """Remove and return last element"""
        if not self.data:
            raise Exception("LinkedList.removeLast: list is empty")
        return self.data.pop()
    
    def get(self, index: int) -> Any:
        """Get element at index"""
        if not isinstance(index, int) or index < 0 or index >= len(self.data):
            raise Exception("LinkedList.get index out of bounds")
        return self.data[index]
    
    def getFirst(self) -> Any:
        """Get first element"""
        if not self.data:
            raise Exception("LinkedList.getFirst: list is empty")
        return self.data[0]
    
    def getLast(self) -> Any:
        """Get last element"""
        if not self.data:
            raise Exception("LinkedList.getLast: list is empty")
        return self.data[-1]
    
    def size(self) -> int:
        """Return size"""
        return len(self.data)
    
    def isEmpty(self) -> bool:
        """Check if empty"""
        return len(self.data) == 0
    
    def clear(self) -> None:
        """Clear all elements"""
        self.data.clear()
    
    def contains(self, value: Any) -> bool:
        """Check if value exists"""
        return value in self.data
    
    def indexOf(self, value: Any) -> int:
        """Return index or -1"""
        try:
            return self.data.index(value)
        except ValueError:
            return -1
    
    def toArray(self) -> list[Any]:
        """Convert to array"""
        return list(self.data)
    
    def reverse(self) -> None:
        """Reverse in place"""
        self.data.reverse()
