import System.utils.Collections

any function main() {
    print("=== Testing new Syntax ===")
    
    // Test 1: Basic new syntax
    let stack = new Collections.Stack()
    stack.push("first")
    stack.push("second")
    print("Stack with new:", stack.peek())
    
    // Test 2: Type annotation on left
    let Collections.Stack stack2 = new Collections.Stack()
    stack2.push("item")
    print("Stack with type annotation:", stack2.peek())
    
    // Test 3: HashMap
    let Collections.HashMap map = new Collections.HashMap()
    map.set("key", "value")
    print("HashMap:", map.get("key"))
    
    // Test 4: Queue
    let Collections.Queue queue = new Collections.Queue()
    queue.enqueue("item")
    print("Queue:", queue.peek())
    
    print("\n=== All new syntax tests passed ===")
}
