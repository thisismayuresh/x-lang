function main() {
    print("=== Queue Tests ===")
    
    // Test 1: Create and basic operations
    print("\nTest 1: Basic operations")
    let queue = Queue.create()
    Queue.enqueue(queue, "first")
    Queue.enqueue(queue, "second")
    Queue.enqueue(queue, "third")
    print("Enqueued three elements")
    print("Size:", Queue.size(queue))
    print("Is empty:", Queue.isEmpty(queue))
    print("Peek:", Queue.peek(queue))
    
    // Test 2: Dequeue operations
    print("\nTest 2: Dequeue operations")
    let dequeued1 = Queue.dequeue(queue)
    let dequeued2 = Queue.dequeue(queue)
    print("Dequeued:", dequeued1)
    print("Dequeued:", dequeued2)
    print("Current peek:", Queue.peek(queue))
    print("Size:", Queue.size(queue))
    
    // Test 3: FIFO behavior
    print("\nTest 3: FIFO behavior")
    let fifo = Queue.create()
    Queue.enqueue(fifo, "a")
    Queue.enqueue(fifo, "b")
    Queue.enqueue(fifo, "c")
    print("Enqueued a, b, c in order")
    print("Dequeue order:")
    while (!Queue.isEmpty(fifo)) {
        print("  ", Queue.dequeue(fifo))
    }
    
    // Test 4: Create with initial array
    print("\nTest 4: Create with initial array")
    let initial = [1, 2, 3, 4, 5]
    let queue2 = Queue.create(initial)
    print("Created from array:", Queue.toArray(queue2))
    print("Size:", Queue.size(queue2))
    
    // Test 5: Clear
    print("\nTest 5: Clear")
    Queue.enqueue(queue, "new")
    print("Size before clear:", Queue.size(queue))
    Queue.clear(queue)
    print("Size after clear:", Queue.size(queue))
    print("Is empty:", Queue.isEmpty(queue))
    
    // Test 6: ToArray
    print("\nTest 6: ToArray")
    let queue3 = Queue.create()
    Queue.enqueue(queue3, "x")
    Queue.enqueue(queue3, "y")
    Queue.enqueue(queue3, "z")
    print("Queue as array:", Queue.toArray(queue3))
    
    print("\n=== All Queue tests completed ===")
}
