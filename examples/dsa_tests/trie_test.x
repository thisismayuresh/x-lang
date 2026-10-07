import System.utils.Collections.Trie

any function main() {
    print("=== Trie Tests ===")
    
    // Test 1: Create and basic insert/search
    print("\nTest 1: Basic insert and search")
    let trie = Trie.create()
    Trie.insert(trie, "hello")
    Trie.insert(trie, "world")
    Trie.insert(trie, "hey")
    print("Inserted: hello, world, hey")
    print("Search 'hello':", Trie.search(trie, "hello"))
    print("Search 'world':", Trie.search(trie, "world"))
    print("Search 'hey':", Trie.search(trie, "hey"))
    print("Search 'he':", Trie.search(trie, "he"))
    print("Size:", Trie.size(trie))
    
    // Test 2: Starts with
    print("\nTest 2: Starts with (prefix search)")
    print("Starts with 'he':", Trie.startsWith(trie, "he"))
    print("Starts with 'wo':", Trie.startsWith(trie, "wo"))
    print("Starts with 'z':", Trie.startsWith(trie, "z"))
    print("Starts with 'hello':", Trie.startsWith(trie, "hello"))
    
    // Test 3: Get all words
    print("\nTest 3: Get all words")
    print("All words in trie:", Trie.getAllWords(trie))
    
    // Test 4: Remove
    print("\nTest 4: Remove")
    let removed = Trie.remove(trie, "hey")
    print("Removed 'hey':", removed)
    print("Search 'hey' after remove:", Trie.search(trie, "hey"))
    print("Starts with 'he' after remove:", Trie.startsWith(trie, "he"))
    print("Size after remove:", Trie.size(trie))
    print("All words:", Trie.getAllWords(trie))
    
    // Test 5: Remove non-existent
    print("\nTest 5: Remove non-existent word")
    let removed2 = Trie.remove(trie, "nonexistent")
    print("Removed 'nonexistent':", removed2)
    print("Size:", Trie.size(trie))
    
    // Test 6: More complex prefixes
    print("\nTest 6: Complex prefix structure")
    let trie2 = Trie.create()
    Trie.insert(trie2, "app")
    Trie.insert(trie2, "apple")
    Trie.insert(trie2, "application")
    Trie.insert(trie2, "apply")
    Trie.insert(trie2, "cat")
    Trie.insert(trie2, "category")
    print("Inserted: app, apple, application, apply, cat, category")
    print("All words:", Trie.getAllWords(trie2))
    print("Starts with 'app':", Trie.startsWith(trie2, "app"))
    print("Starts with 'cat':", Trie.startsWith(trie2, "cat"))
    
    // Test 7: Remove with shared prefix
    print("\nTest 7: Remove with shared prefix")
    Trie.remove(trie2, "app")
    print("After removing 'app':")
    print("All words:", Trie.getAllWords(trie2))
    print("Search 'apple':", Trie.search(trie2, "apple"))
    print("Starts with 'app':", Trie.startsWith(trie2, "app"))
    
    // Test 8: Clear
    print("\nTest 8: Clear")
    print("Size before clear:", Trie.size(trie2))
    Trie.clear(trie2)
    print("Size after clear:", Trie.size(trie2))
    print("Is empty:", Trie.isEmpty(trie2))
    print("All words:", Trie.getAllWords(trie2))
    
    // Test 9: Empty trie operations
    print("\nTest 9: Empty trie operations")
    let empty = Trie.create()
    print("Empty trie size:", Trie.size(empty))
    print("Empty trie is empty:", Trie.isEmpty(empty))
    print("Search in empty:", Trie.search(empty, "test"))
    print("Starts with in empty:", Trie.startsWith(empty, "test"))
    
    print("\n=== All Trie tests completed ===")
}
