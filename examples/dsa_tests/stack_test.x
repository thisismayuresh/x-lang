function main() {
    print("=== Stack Tests ===")
    
    // Test 1: Create and basic operations
    print("\nTest 1: Basic operations")
    let stack = Stack.create()
    System.utils.Collections.Stack.push(stack, "first")
    System.utils.Collections.Stack.push(stack, "second")
    System.utils.Collections.Stack.push(stack, "third")
    print("Pushed three elements")
    print("Size:", System.utils.Collections.Stack.size(stack))
    print("Is empty:", System.utils.Collections.Stack.isEmpty(stack))
    print("Peek:", System.utils.Collections.Stack.peek(stack))
    
    // Test 2: Pop operations
    print("\nTest 2: Pop operations")
    let popped1 = System.utils.Collections.Stack.pop(stack)
    let popped2 = System.utils.Collections.Stack.pop(stack)
    print("Popped:", popped1)
    print("Popped:", popped2)
    print("Current peek:", System.utils.Collections.Stack.peek(stack))
    print("Size:", System.utils.Collections.Stack.size(stack))
    
    // Test 3: Create with initial array
    print("\nTest 3: Create with initial array")
    let initial = [1, 2, 3, 4, 5]
    let stack2 = System.utils.Collections.Stack.create(initial)
    print("Created from array:", System.utils.Collections.Stack.toArray(stack2))
    print("Size:", System.utils.Collections.Stack.size(stack2))
    
    // Test 4: LIFO behavior
    print("\nTest 4: LIFO behavior")
    let lifo = Stack.create()
    Stack.push(lifo, "a")
    Stack.push(lifo, "b")
    Stack.push(lifo, "c")
    print("Pushed a, b, c in order")
    print("Pop order:")
    while (!Stack.isEmpty(lifo)) {
        print("  ", Stack.pop(lifo))
    }
    
    // Test 5: Clear
    print("\nTest 5: Clear")
    Stack.push(stack, "new")
    print("Size before clear:", Stack.size(stack))
    Stack.clear(stack)
    print("Size after clear:", Stack.size(stack))
    print("Is empty:", Stack.isEmpty(stack))
    
    // Test 6: ToArray
    print("\nTest 6: ToArray")
    let stack3 = Stack.create()
    Stack.push(stack3, "x")
    Stack.push(stack3, "y")
    Stack.push(stack3, "z")
    print("Stack as array:", Stack.toArray(stack3))
    
    print("\n=== All Stack tests completed ===")
}
