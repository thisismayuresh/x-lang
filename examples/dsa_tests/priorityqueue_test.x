any function main() {
    print("=== PriorityQueue Tests ===")
    
    // Test 1: Create and basic operations
    print("\nTest 1: Basic operations with numbers")
    let pq = PriorityQueue.create()
    PriorityQueue.enqueue(pq, 5)
    PriorityQueue.enqueue(pq, 2)
    PriorityQueue.enqueue(pq, 8)
    PriorityQueue.enqueue(pq, 1)
    PriorityQueue.enqueue(pq, 10)
    print("Enqueued: 5, 2, 8, 1, 10")
    print("Size:", PriorityQueue.size(pq))
    print("Peek (should be smallest):", PriorityQueue.peek(pq))
    
    // Test 2: Dequeue in priority order
    print("\nTest 2: Dequeue in priority order")
    print("Dequeue order (ascending):")
    while (!PriorityQueue.isEmpty(pq)) {
        print("  ", PriorityQueue.dequeue(pq))
    }
    
    // Test 3: With strings (lexicographic order)
    print("\nTest 3: String priority (lexicographic)")
    let strPq = PriorityQueue.create()
    PriorityQueue.enqueue(strPq, "zebra")
    PriorityQueue.enqueue(strPq, "apple")
    PriorityQueue.enqueue(strPq, "mango")
    PriorityQueue.enqueue(strPq, "banana")
    print("Enqueued: zebra, apple, mango, banana")
    print("Dequeue order:")
    while (!PriorityQueue.isEmpty(strPq)) {
        print("  ", PriorityQueue.dequeue(strPq))
    }
    
    // Test 4: Mixed operations
    print("\nTest 4: Mixed operations")
    let mixed = PriorityQueue.create()
    PriorityQueue.enqueue(mixed, 3)
    PriorityQueue.enqueue(mixed, 1)
    print("After enqueue 3, 1:")
    print("Peek:", PriorityQueue.peek(mixed))
    PriorityQueue.enqueue(mixed, 2)
    print("After enqueue 2:")
    print("Peek:", PriorityQueue.peek(mixed))
    print("Dequeue:", PriorityQueue.dequeue(mixed))
    print("New peek:", PriorityQueue.peek(mixed))
    
    // Test 5: Clear
    print("\nTest 5: Clear")
    PriorityQueue.enqueue(mixed, 100)
    print("Size before clear:", PriorityQueue.size(mixed))
    PriorityQueue.clear(mixed)
    print("Size after clear:", PriorityQueue.size(mixed))
    print("Is empty:", PriorityQueue.isEmpty(mixed))
    
    // Test 6: ToArray
    print("\nTest 6: ToArray")
    let pq2 = PriorityQueue.create()
    PriorityQueue.enqueue(pq2, 5)
    PriorityQueue.enqueue(pq2, 3)
    PriorityQueue.enqueue(pq2, 7)
    print("PriorityQueue as array:", PriorityQueue.toArray(pq2))
    
    print("\n=== All PriorityQueue tests completed ===")
}
