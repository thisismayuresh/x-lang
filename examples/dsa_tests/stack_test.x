any function main() {
    print("=== Stack Tests ===")
    
    // Test 1: Create and basic operations
    print("\nTest 1: Basic operations")
    let stack = new Stack()
    stack.push("first")
    stack.push("second")
    stack.push("third")
    print("Pushed three elements")
    print("Size:", stack.size())
    print("Is empty:", stack.isEmpty())
    print("Peek:", stack.peek())
    
    // Test 2: Pop operations
    print("\nTest 2: Pop operations")
    let popped1 = stack.pop()
    let popped2 = stack.pop()
    print("Popped:", popped1)
    print("Popped:", popped2)
    print("Current peek:", stack.peek())
    print("Size:", stack.size())
    
    // Test 3: Create with initial array
    print("\nTest 3: Create with initial array")
    let initial = [1, 2, 3, 4, 5]
    let stack2 = new Stack(initial)
    print("Created from array:", stack2.toArray())
    print("Size:", stack2.size())
    
    // Test 4: LIFO behavior
    print("\nTest 4: LIFO behavior")
    let lifo = new Stack()
    lifo.push("a")
    lifo.push("b")
    lifo.push("c")
    print("Pushed a, b, c in order")
    print("Pop order:")
    while (!lifo.isEmpty()) {
        print("  ", lifo.pop())
    }
    
    // Test 5: Clear
    print("\nTest 5: Clear")
    stack.push("new")
    print("Size before clear:", stack.size())
    stack.clear()
    print("Size after clear:", stack.size())
    print("Is empty:", stack.isEmpty())
    
    // Test 6: ToArray
    print("\nTest 6: ToArray")
    let stack3 = new Stack()
    stack3.push("x")
    stack3.push("y")
    stack3.push("z")
    print("Stack as array:", stack3.toArray())
    
    print("\n=== All Stack tests completed ===")
}
