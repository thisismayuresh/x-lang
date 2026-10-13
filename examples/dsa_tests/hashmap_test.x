import System.utils.Collections.HashMap

any function main() {
    print("=== HashMap Tests ===")
    
    // Test 1: Create and basic operations
    print("\nTest 1: Basic operations")
    let map = new HashMap()
    map.set("name", "Alice")
    map.set("age", 30)
    map.set(42, "number key")
    print("Set name, age, and number key")
    print("Get name:", map.get("name"))
    print("Get age:", map.get("age"))
    print("Get 42:", map.get(42))
    print("Has name:", map.has("name"))
    print("Has unknown:", map.has("unknown"))
    print("Size:", map.size())
    
    // Test 2: getOrDefault
    print("\nTest 2: getOrDefault")
    print("Get existing with default:", map.getOrDefault("name", "default"))
    print("Get missing with default:", map.getOrDefault("missing", "default"))
    
    // Test 3: computeIfAbsent
    print("\nTest 3: computeIfAbsent")
    let visited = new HashMap()
    function getCounter(string key) {
        return key.length * 10
    }
    let count1 = visited.computeIfAbsent("alice", getCounter)
    let count2 = visited.computeIfAbsent("alice", getCounter)
    print("First compute:", count1)
    print("Second compute (cached):", count2)
    print("Visited size:", visited.size())
    
    // Test 4: computeIfPresent
    print("\nTest 4: computeIfPresent")
    let scores = new HashMap()
    scores.set("player1", 100)
    function doubleScore(string key, int value) {
        return value * 2
    }
    scores.computeIfPresent("player1", doubleScore)
    print("Doubled score:", scores.get("player1"))
    scores.computeIfPresent("player2", doubleScore)
    print("Non-existent key not added:", scores.has("player2"))
    
    // Test 5: Keys, values, entries
    print("\nTest 5: Keys, values, entries")
    print("Keys:", map.keys())
    print("Values:", map.values())
    print("Entries:", map.entries())
    
    // Test 6: Remove
    print("\nTest 6: Remove")
    let removed = map.remove("age")
    print("Removed value:", removed)
    print("Size after remove:", map.size())
    print("Has age after remove:", map.has("age"))
    
    // Test 7: Merge
    print("\nTest 7: Merge")
    let map2 = new HashMap()
    map2.set("city", "NYC")
    map2.set("country", "USA")
    let merged = map.merge(map2)
    print("Merged size:", merged.size())
    print("Merged entries:", merged.entries())
    
    // Test 8: Filter
    print("\nTest 8: Filter")
    function isLongEntry(string[] entry) {
        return entry[0].length > 3
    }
    let filtered = merged.filter(isLongEntry)
    print("Filtered (key length > 3):", filtered.entries())
    
    // Test 9: Map
    print("\nTest 9: Map (transform)")
    function uppercaseKey(string[] entry) {
        return [entry[0].toUpperCase(), entry[1]]
    }
    let mapped = merged.map(uppercaseKey)
    print("Mapped (uppercase keys):", mapped.entries())
    
    // Test 10: Reduce
    print("\nTest 10: Reduce")
    function sumValues(int accumulator, string[] entry) {
        if (typeOf(entry[1]) === "number") {
            return accumulator + entry[1]
        }
        return accumulator
    }
    let sum = merged.reduce(0, sumValues)
    print("Sum of numeric values:", sum)
    
    // Test 11: putAll
    print("\nTest 11: putAll")
    let target = new HashMap()
    target.set("existing", "value")
    target.putAll(map2)
    print("Target after putAll:", target.entries())
    
    // Test 12: Clear
    print("\nTest 12: Clear")
    map.clear()
    print("Size after clear:", map.size())
    
    print("\n=== All HashMap tests completed ===")
}
