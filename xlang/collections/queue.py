"""
Queue implementation for X Language
"""
from typing import Any


class QueueClass:
    """X language Queue class implementation"""
    
    def __init__(self, initial_array: list = None):
        self.data = list(initial_array) if initial_array else []
    
    def enqueue(self, value: Any) -> None:
        """Add to back of queue"""
        self.data.append(value)
    
    def dequeue(self) -> Any:
        """Remove and return front element"""
        if not self.data:
            raise Exception("Queue.dequeue: queue is empty")
        return self.data.pop(0)
    
    def peek(self) -> Any:
        """Return front element without removing"""
        if not self.data:
            raise Exception("Queue.peek: queue is empty")
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
