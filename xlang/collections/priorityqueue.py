"""
PriorityQueue implementation for X Language
"""
from typing import Any


class PriorityQueueClass:
    """X language PriorityQueue class implementation"""
    
    def __init__(self, comparator=None):
        self.data = []
        self.comparator = comparator
    
    def enqueue(self, value: Any) -> None:
        """Add value (maintains order)"""
        self.data.append(value)
        self.data.sort()
    
    def dequeue(self) -> Any:
        """Remove and return minimum element"""
        if not self.data:
            raise Exception("PriorityQueue.dequeue: queue is empty")
        return self.data.pop(0)
    
    def peek(self) -> Any:
        """Return minimum element without removing"""
        if not self.data:
            raise Exception("PriorityQueue.peek: queue is empty")
        return self.data[0]
    
    def size(self) -> int:
        """Return queue size"""
        return len(self.data)
    
    def isEmpty(self) -> bool:
        """Check if empty"""
        return len(self.data) == 0
    
    def clear(self) -> None:
        """Clear queue"""
        self.data.clear()
    
    def toArray(self) -> list[Any]:
        """Convert to array"""
        return list(self.data)
