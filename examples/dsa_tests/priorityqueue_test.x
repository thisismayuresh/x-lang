any function main() {
    print("=== PriorityQueue Tests ===")
    
    // Test 1: Create and basic operations
    print("\nTest 1: Basic operations with numbers")
    let pq = new PriorityQueue()
    pq.enqueue(5)
    pq.enqueue(2)
    pq.enqueue(8)
    pq.enqueue(1)
    pq.enqueue(10)
    print("Enqueued: 5, 2, 8, 1, 10")
    print("Size:", pq.size())
    print("Peek (should be smallest):", pq.peek())
    
    // Test 2: Dequeue in priority order
    print("\nTest 2: Dequeue in priority order")
    print("Dequeue order (ascending):")
    while (!pq.isEmpty()) {
        print("  ", pq.dequeue())
    }
    
    // Test 3: With strings (lexicographic order)
    print("\nTest 3: String priority (lexicographic)")
    let strPq = new PriorityQueue()
    strPq.enqueue("zebra")
    strPq.enqueue("apple")
    strPq.enqueue("mango")
    strPq.enqueue("banana")
    print("Enqueued: zebra, apple, mango, banana")
    print("Dequeue order:")
    while (!strPq.isEmpty()) {
        print("  ", strPq.dequeue())
    }
    
    // Test 4: Mixed operations
    print("\nTest 4: Mixed operations")
    let mixed = new PriorityQueue()
    mixed.enqueue(3)
    mixed.enqueue(1)
    print("After enqueue 3, 1:")
    print("Peek:", mixed.peek())
    mixed.enqueue(2)
    print("After enqueue 2:")
    print("Peek:", mixed.peek())
    print("Dequeue:", mixed.dequeue())
    print("New peek:", mixed.peek())
    
    // Test 5: Clear
    print("\nTest 5: Clear")
    mixed.enqueue(100)
    print("Size before clear:", mixed.size())
    mixed.clear()
    print("Size after clear:", mixed.size())
    print("Is empty:", mixed.isEmpty())
    
    // Test 6: ToArray
    print("\nTest 6: ToArray")
    let pq2 = new PriorityQueue()
    pq2.enqueue(5)
    pq2.enqueue(3)
    pq2.enqueue(7)
    print("PriorityQueue as array:", pq2.toArray())
    
    print("\n=== All PriorityQueue tests completed ===")
}
