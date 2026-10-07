// Sample X language file for testing syntax highlighting

// Imports
import System.io.Console;
import System.Collections.HashMap;

// Types
type UserId = int;
type UserMap = HashMap<string, User>;

// Interface
interface Serializable {
    void serialize();
    void deserialize(string data);
}

// Enum
enum Status {
    ACTIVE,
    INACTIVE,
    PENDING
}

// Class with generics
class Repository<T> implements Serializable {
    private HashMap<UserId, T> items = new HashMap<UserId, T>();
    private int nextId = 0;
    
    // Constructor
    public Repository() {
        print("Repository initialized");
    }
    
    // Method with generics
    public T add(T item): T {
        let id = this.nextId++;
        this.items.put(id, item);
        return item;
    }
    
    public T? get(UserId id): T? {
        return this.items.get(id);
    }
    
    public void remove(UserId id) {
        this.items.remove(id);
    }
    
    // Interface implementation
    public void serialize() {
        print("Serializing repository with " + this.items.size() + " items");
    }
    
    public void deserialize(string data) {
        print("Deserializing: " + data);
    }
}

// Async function
async function fetchUser(id: UserId): Promise<User> {
    await sleep(100);
    return new User(id, "User " + id);
}

// Main function
function main() {
    let repo = new Repository<User>();
    
    // Loop
    for (let i = 0; i < 10; i++) {
        let user = new User(i, "User " + i);
        repo.add(user);
    }
    
    // Conditionals
    let status = Status.ACTIVE;
    match (status) {
        case Status.ACTIVE => print("Active"),
        case Status.INACTIVE => print("Inactive"),
        default => print("Unknown")
    }
    
    // Template strings
    let message = `Repository has ${repo.items.size()} users`;
    print(message);
    
    // Try-catch
    try {
        let result = riskyOperation();
        print("Result: " + result);
    } catch (e) {
        print("Error: " + e.message);
    } finally {
        print("Cleanup");
    }
    
    // Lambda/arrow functions
    let numbers = [1, 2, 3, 4, 5];
    let doubled = numbers.map(x => x * 2);
    let evens = numbers.filter(x => x % 2 == 0);
    let sum = numbers.reduce((a, b) => a + b, 0);
    
    print("Doubled: " + doubled);
    print("Evens: " + evens);
    print("Sum: " + sum);
}

// Decorators
@deprecated
@experimental
function oldApi() {
    print("Old API");
}

// Run
main();