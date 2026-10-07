"""
Stack implementation for X Language
"""
from typing import Any


class StackClass:
    """X language Stack class implementation"""
    
    def __init__(self, initial_array: list = None):
        self.data = list(initial_array) if initial_array else []
    
    def push(self, value: Any) -> None:
        """Push value onto stack"""
        self.data.append(value)
    
    def pop(self) -> Any:
        """Pop and return top value"""
        if not self.data:
            raise Exception("Stack.pop: stack is empty")
        return self.data.pop()
    
    def peek(self) -> Any:
        """Return top value without removing"""
        if not self.data:
            raise Exception("Stack.peek: stack is empty")
        return self.data[-1]
    
    def size(self) -> int:
        """Return stack size"""
        return len(self.data)
    
    def isEmpty(self) -> bool:
        """Check if empty"""
        return len(self.data) == 0
    
    def clear(self) -> None:
        """Clear stack"""
        self.data.clear()
    
    def toArray(self) -> list[Any]:
        """Convert to array"""
        return list(self.data)
