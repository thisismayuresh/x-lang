any function main() {
    print("=== LinkedList Tests ===")
    
    // Test 1: Create and basic operations
    print("\nTest 1: Basic operations")
    let list = LinkedList.create()
    LinkedList.add(list, "first")
    LinkedList.add(list, "second")
    LinkedList.add(list, "third")
    print("Added three elements")
    print("Size:", LinkedList.size(list))
    print("Is empty:", LinkedList.isEmpty(list))
    print("Get index 0:", LinkedList.get(list, 0))
    print("Get index 1:", LinkedList.get(list, 1))
    print("Get index 2:", LinkedList.get(list, 2))
    
    // Test 2: addFirst and addLast
    print("\nTest 2: addFirst and addLast")
    LinkedList.addFirst(list, "zero")
    LinkedList.addLast(list, "fourth")
    print("After addFirst and addLast:")
    print("First:", LinkedList.getFirst(list))
    print("Last:", LinkedList.getLast(list))
    print("Size:", LinkedList.size(list))
    
    // Test 3: Contains and indexOf
    print("\nTest 3: Contains and indexOf")
    print("Contains 'second':", LinkedList.contains(list, "second"))
    print("Contains 'missing':", LinkedList.contains(list, "missing"))
    print("Index of 'second':", LinkedList.indexOf(list, "second"))
    print("Index of 'missing':", LinkedList.indexOf(list, "missing"))
    
    // Test 4: Remove
    print("\nTest 4: Remove")
    let removed = LinkedList.remove(list, "second")
    print("Removed 'second':", removed)
    print("Size after remove:", LinkedList.size(list))
    print("Index of 'second' after remove:", LinkedList.indexOf(list, "second"))
    
    // Test 5: removeFirst and removeLast
    print("\nTest 5: removeFirst and removeLast")
    let first = LinkedList.removeFirst(list)
    let last = LinkedList.removeLast(list)
    print("Removed first:", first)
    print("Removed last:", last)
    print("Current first:", LinkedList.getFirst(list))
    print("Current last:", LinkedList.getLast(list))
    print("Size:", LinkedList.size(list))
    
    // Test 6: ToArray
    print("\nTest 6: ToArray")
    let array = LinkedList.toArray(list)
    print("Array:", array)
    
    // Test 7: Reverse
    print("\nTest 7: Reverse")
    LinkedList.reverse(list)
    print("After reverse:")
    print("First:", LinkedList.getFirst(list))
    print("Last:", LinkedList.getLast(list))
    print("Array:", LinkedList.toArray(list))
    
    // Test 8: Create with initial array
    print("\nTest 8: Create with initial array")
    let initial = [10, 20, 30, 40]
    let list2 = LinkedList.create(initial)
    print("Created from array:", LinkedList.toArray(list2))
    print("Size:", LinkedList.size(list2))
    
    // Test 9: Clear
    print("\nTest 9: Clear")
    LinkedList.clear(list)
    print("Size after clear:", LinkedList.size(list))
    print("Is empty:", LinkedList.isEmpty(list))
    
    // Test 10: Error handling
    print("\nTest 10: Error handling")
    let empty = LinkedList.create()
    print("Empty list size:", LinkedList.size(empty))
    print("Try removeFirst on empty (should error):")
    // This will error, demonstrating error handling
    // LinkedList.removeFirst(empty)
    
    print("\n=== All LinkedList tests completed ===")
}
