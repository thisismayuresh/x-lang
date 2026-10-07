import System.utils.Collections

any function main() {
    print("=== Testing Import Syntax ===")
    
    // Test with import
    let map = Collections.HashMap.create()
    Collections.HashMap.set(map, "key", "value")
    print("HashMap with import:", Collections.HashMap.get(map, "key"))
    
    let stack = Collections.Stack.create()
    Collections.Stack.push(stack, "item")
    print("Stack with import:", Collections.Stack.peek(stack))
    
    let queue = Collections.Queue.create()
    Collections.Queue.enqueue(queue, "item")
    print("Queue with import:", Collections.Queue.peek(queue))
    
    print("\n=== All import tests passed ===")
}
