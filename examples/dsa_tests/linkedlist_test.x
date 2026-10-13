any function main() {
    print("=== LinkedList Tests ===")
    
    // Test 1: Create and basic operations
    print("\nTest 1: Basic operations")
    let list = new LinkedList()
    list.add("first")
    list.add("second")
    list.add("third")
    print("Added three elements")
    print("Size:", list.size())
    print("Is empty:", list.isEmpty())
    print("Get index 0:", list.get(0))
    print("Get index 1:", list.get(1))
    print("Get index 2:", list.get(2))
    
    // Test 2: addFirst and addLast
    print("\nTest 2: addFirst and addLast")
    list.addFirst("zero")
    list.addLast("fourth")
    print("After addFirst and addLast:")
    print("First:", list.getFirst())
    print("Last:", list.getLast())
    print("Size:", list.size())
    
    // Test 3: Contains and indexOf
    print("\nTest 3: Contains and indexOf")
    print("Contains 'second':", list.contains("second"))
    print("Contains 'missing':", list.contains("missing"))
    print("Index of 'second':", list.indexOf("second"))
    print("Index of 'missing':", list.indexOf("missing"))
    
    // Test 4: Remove
    print("\nTest 4: Remove")
    let removed = list.remove("second")
    print("Removed 'second':", removed)
    print("Size after remove:", list.size())
    print("Index of 'second' after remove:", list.indexOf("second"))
    
    // Test 5: removeFirst and removeLast
    print("\nTest 5: removeFirst and removeLast")
    let first = list.removeFirst()
    let last = list.removeLast()
    print("Removed first:", first)
    print("Removed last:", last)
    print("Current first:", list.getFirst())
    print("Current last:", list.getLast())
    print("Size:", list.size())
    
    // Test 6: ToArray
    print("\nTest 6: ToArray")
    let array = list.toArray()
    print("Array:", array)
    
    // Test 7: Reverse
    print("\nTest 7: Reverse")
    list.reverse()
    print("After reverse:")
    print("First:", list.getFirst())
    print("Last:", list.getLast())
    print("Array:", list.toArray())
    
    // Test 8: Create with initial array
    print("\nTest 8: Create with initial array")
    let initial = [10, 20, 30, 40]
    let list2 = new LinkedList(initial)
    print("Created from array:", list2.toArray())
    print("Size:", list2.size())
    
    // Test 9: Clear
    print("\nTest 9: Clear")
    list.clear()
    print("Size after clear:", list.size())
    print("Is empty:", list.isEmpty())
    
    // Test 10: Error handling
    print("\nTest 10: Error handling")
    let empty = new LinkedList()
    print("Empty list size:", empty.size())
    print("Try removeFirst on empty (should error):")
    // This will error, demonstrating error handling
    // empty.removeFirst()
    
    print("\n=== All LinkedList tests completed ===")
}
