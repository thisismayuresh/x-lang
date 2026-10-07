import System.utils.Collections

any function main() {
    print("=== Testing new Syntax ===")
    
    // Test 1: Basic new syntax
    let stack = new Collections.Stack()
    Collections.Stack.push(stack, "first")
    Collections.Stack.push(stack, "second")
    print("Stack with new:", Collections.Stack.peek(stack))
    
    // Test 2: Type annotation on left
    let Collections.Stack stack2 = new Collections.Stack()
    Collections.Stack.push(stack2, "item")
    print("Stack with type annotation:", Collections.Stack.peek(stack2))
    
    // Test 3: HashMap
    let Collections.HashMap map = new Collections.HashMap()
    Collections.HashMap.set(map, "key", "value")
    print("HashMap:", Collections.HashMap.get(map, "key"))
    
    // Test 4: Queue
    let Collections.Queue queue = new Collections.Queue()
    Collections.Queue.enqueue(queue, "item")
    print("Queue:", Collections.Queue.peek(queue))
    
    print("\n=== All new syntax tests passed ===")
}
