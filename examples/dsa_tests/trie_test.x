import System.utils.Collections.Trie

any function main() {
    print("=== Trie Tests ===")
    
    // Test 1: Create and basic insert/search
    print("\nTest 1: Basic insert and search")
    let trie = new Trie()
    trie.insert("hello")
    trie.insert("world")
    trie.insert("hey")
    print("Inserted: hello, world, hey")
    print("Search 'hello':", trie.search("hello"))
    print("Search 'world':", trie.search("world"))
    print("Search 'hey':", trie.search("hey"))
    print("Search 'he':", trie.search("he"))
    print("Size:", trie.size())
    
    // Test 2: Starts with
    print("\nTest 2: Starts with (prefix search)")
    print("Starts with 'he':", trie.startsWith("he"))
    print("Starts with 'wo':", trie.startsWith("wo"))
    print("Starts with 'z':", trie.startsWith("z"))
    print("Starts with 'hello':", trie.startsWith("hello"))
    
    // Test 3: Get all words
    print("\nTest 3: Get all words")
    print("All words in trie:", trie.getAllWords())
    
    // Test 4: Remove
    print("\nTest 4: Remove")
    let removed = trie.remove("hey")
    print("Removed 'hey':", removed)
    print("Search 'hey' after remove:", trie.search("hey"))
    print("Starts with 'he' after remove:", trie.startsWith("he"))
    print("Size after remove:", trie.size())
    print("All words:", trie.getAllWords())
    
    // Test 5: Remove non-existent
    print("\nTest 5: Remove non-existent word")
    let removed2 = trie.remove("nonexistent")
    print("Removed 'nonexistent':", removed2)
    print("Size:", trie.size())
    
    // Test 6: More complex prefixes
    print("\nTest 6: Complex prefix structure")
    let trie2 = new Trie()
    trie2.insert("app")
    trie2.insert("apple")
    trie2.insert("application")
    trie2.insert("apply")
    trie2.insert("cat")
    trie2.insert("category")
    print("Inserted: app, apple, application, apply, cat, category")
    print("All words:", trie2.getAllWords())
    print("Starts with 'app':", trie2.startsWith("app"))
    print("Starts with 'cat':", trie2.startsWith("cat"))
    
    // Test 7: Remove with shared prefix
    print("\nTest 7: Remove with shared prefix")
    trie2.remove("app")
    print("After removing 'app':")
    print("All words:", trie2.getAllWords())
    print("Search 'apple':", trie2.search("apple"))
    print("Starts with 'app':", trie2.startsWith("app"))
    
    // Test 8: Clear
    print("\nTest 8: Clear")
    print("Size before clear:", trie2.size())
    trie2.clear()
    print("Size after clear:", trie2.size())
    print("Is empty:", trie2.isEmpty())
    print("All words:", trie2.getAllWords())
    
    // Test 9: Empty trie operations
    print("\nTest 9: Empty trie operations")
    let empty = new Trie()
    print("Empty trie size:", empty.size())
    print("Empty trie is empty:", empty.isEmpty())
    print("Search in empty:", empty.search("test"))
    print("Starts with in empty:", empty.startsWith("test"))
    
    print("\n=== All Trie tests completed ===")
}
