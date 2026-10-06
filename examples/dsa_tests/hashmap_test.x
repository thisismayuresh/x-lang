function main() {
    print("=== HashMap Tests ===")
    
    // Test 1: Create and basic operations
    print("\nTest 1: Basic operations")
    let map = System.utils.Collections.HashMap.create()
    System.utils.Collections.HashMap.set(map, "name", "Alice")
    System.utils.Collections.HashMap.set(map, "age", 30)
    System.utils.Collections.HashMap.set(map, 42, "number key")
    print("Set name, age, and number key")
    print("Get name:", System.utils.Collections.HashMap.get(map, "name"))
    print("Get age:", System.utils.Collections.HashMap.get(map, "age"))
    print("Get 42:", System.utils.Collections.HashMap.get(map, 42))
    print("Has name:", System.utils.Collections.HashMap.has(map, "name"))
    print("Has unknown:", System.utils.Collections.HashMap.has(map, "unknown"))
    print("Size:", System.utils.Collections.HashMap.size(map))
    
    // Test 2: getOrDefault
    print("\nTest 2: getOrDefault")
    print("Get existing with default:", System.utils.Collections.HashMap.getOrDefault(map, "name", "default"))
    print("Get missing with default:", System.utils.Collections.HashMap.getOrDefault(map, "missing", "default"))
    
    // Test 3: computeIfAbsent
    print("\nTest 3: computeIfAbsent")
    let visited = System.utils.Collections.HashMap.create()
    function getCounter(string key) {
        return key.length * 10
    }
    let count1 = System.utils.Collections.HashMap.computeIfAbsent(visited, "alice", getCounter)
    let count2 = System.utils.Collections.HashMap.computeIfAbsent(visited, "alice", getCounter)
    print("First compute:", count1)
    print("Second compute (cached):", count2)
    print("Visited size:", System.utils.Collections.HashMap.size(visited))
    
    // Test 4: computeIfPresent
    print("\nTest 4: computeIfPresent")
    let scores = System.utils.Collections.HashMap.create()
    System.utils.Collections.HashMap.set(scores, "player1", 100)
    function doubleScore(string key, int value) {
        return value * 2
    }
    System.utils.Collections.HashMap.computeIfPresent(scores, "player1", doubleScore)
    print("Doubled score:", System.utils.Collections.HashMap.get(scores, "player1"))
    System.utils.Collections.HashMap.computeIfPresent(scores, "player2", doubleScore)
    print("Non-existent key not added:", System.utils.Collections.HashMap.has(scores, "player2"))
    
    // Test 5: Keys, values, entries
    print("\nTest 5: Keys, values, entries")
    print("Keys:", System.utils.Collections.HashMap.keys(map))
    print("Values:", System.utils.Collections.HashMap.values(map))
    print("Entries:", System.utils.Collections.HashMap.entries(map))
    
    // Test 6: Remove
    print("\nTest 6: Remove")
    let removed = System.utils.Collections.HashMap.remove(map, "age")
    print("Removed value:", removed)
    print("Size after remove:", System.utils.Collections.HashMap.size(map))
    print("Has age after remove:", System.utils.Collections.HashMap.has(map, "age"))
    
    // Test 7: Merge
    print("\nTest 7: Merge")
    let map2 = System.utils.Collections.HashMap.create()
    System.utils.Collections.HashMap.set(map2, "city", "NYC")
    System.utils.Collections.HashMap.set(map2, "country", "USA")
    let merged = System.utils.Collections.HashMap.merge(map, map2)
    print("Merged size:", System.utils.Collections.HashMap.size(merged))
    print("Merged entries:", System.utils.Collections.HashMap.entries(merged))
    
    // Test 8: Filter
    print("\nTest 8: Filter")
    function isLongEntry(string[] entry) {
        return entry[0].length > 3
    }
    let filtered = System.utils.Collections.HashMap.filter(merged, isLongEntry)
    print("Filtered (key length > 3):", System.utils.Collections.HashMap.entries(filtered))
    
    // Test 9: Map
    print("\nTest 9: Map (transform)")
    function uppercaseKey(string[] entry) {
        return [entry[0].toUpperCase(), entry[1]]
    }
    let mapped = System.utils.Collections.HashMap.map(merged, uppercaseKey)
    print("Mapped (uppercase keys):", System.utils.Collections.HashMap.entries(mapped))
    
    // Test 10: Reduce
    print("\nTest 10: Reduce")
    function sumValues(int accumulator, string[] entry) {
        if (typeOf(entry[1]) === "number") {
            return accumulator + entry[1]
        }
        return accumulator
    }
    let sum = System.utils.Collections.HashMap.reduce(merged, 0, sumValues)
    print("Sum of numeric values:", sum)
    
    // Test 11: putAll
    print("\nTest 11: putAll")
    let target = System.utils.Collections.HashMap.create()
    System.utils.Collections.HashMap.set(target, "existing", "value")
    System.utils.Collections.HashMap.putAll(target, map2)
    print("Target after putAll:", System.utils.Collections.HashMap.entries(target))
    
    // Test 12: Clear
    print("\nTest 12: Clear")
    System.utils.Collections.HashMap.clear(map)
    print("Size after clear:", System.utils.Collections.HashMap.size(map))
    
    print("\n=== All HashMap tests completed ===")
}
