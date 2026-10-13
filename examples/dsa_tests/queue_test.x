any function main() {
    print("=== Queue Tests ===")
    
    // Test 1: Create and basic operations
    print("\nTest 1: Basic operations")
    let queue = new Queue()
    queue.enqueue("first")
    queue.enqueue("second")
    queue.enqueue("third")
    print("Enqueued three elements")
    print("Size:", queue.size())
    print("Is empty:", queue.isEmpty())
    print("Peek:", queue.peek())
    
    // Test 2: Dequeue operations
    print("\nTest 2: Dequeue operations")
    let dequeued1 = queue.dequeue()
    let dequeued2 = queue.dequeue()
    print("Dequeued:", dequeued1)
    print("Dequeued:", dequeued2)
    print("Current peek:", queue.peek())
    print("Size:", queue.size())
    
    // Test 3: FIFO behavior
    print("\nTest 3: FIFO behavior")
    let fifo = new Queue()
    fifo.enqueue("a")
    fifo.enqueue("b")
    fifo.enqueue("c")
    print("Enqueued a, b, c in order")
    print("Dequeue order:")
    while (!fifo.isEmpty()) {
        print("  ", fifo.dequeue())
    }
    
    // Test 4: Create with initial array
    print("\nTest 4: Create with initial array")
    let initial = [1, 2, 3, 4, 5]
    let queue2 = new Queue(initial)
    print("Created from array:", queue2.toArray())
    print("Size:", queue2.size())
    
    // Test 5: Clear
    print("\nTest 5: Clear")
    queue.enqueue("new")
    print("Size before clear:", queue.size())
    queue.clear()
    print("Size after clear:", queue.size())
    print("Is empty:", queue.isEmpty())
    
    // Test 6: ToArray
    print("\nTest 6: ToArray")
    let queue3 = new Queue()
    queue3.enqueue("x")
    queue3.enqueue("y")
    queue3.enqueue("z")
    print("Queue as array:", queue3.toArray())
    
    print("\n=== All Queue tests completed ===")
}
