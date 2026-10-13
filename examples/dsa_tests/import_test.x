import System.utils.Collections

any function main() {
    print("=== Testing Import Syntax ===")
    
    // Test with import
    let map = new Collections.HashMap()
    map.set("key", "value")
    print("HashMap with import:", map.get("key"))
    
    let stack = new Collections.Stack()
    stack.push("item")
    print("Stack with import:", stack.peek())
    
    let queue = new Collections.Queue()
    queue.enqueue("item")
    print("Queue with import:", queue.peek())
    
    print("\n=== All import tests passed ===")
}
