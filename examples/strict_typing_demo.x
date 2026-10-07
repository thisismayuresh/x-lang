import System.io.Console

// ============================================
// STRICT TYPING DEMONSTRATION (WORKING)
// ============================================
// Run with: python -m xlang examples/strict_typing_demo.x --strict_typing=true
// ============================================

// ✓ VALID: Standalone functions with return type BEFORE function keyword
int function add(int a, int b) {
    return a + b;
}

string function greet(string name) {
    return "Hello, " + name;
}

float function calculateArea(float width, float height) {
    return width * height;
}

// ✓ VALID: Class with typed fields and methods
class Person {
    string name;
    int age;
    
    void Person(string name, int age) {
        this.name = name;
        this.age = age;
    }
    
    string getName() {
        return this.name;
    }
    
    int getAge() {
        return this.age;
    }
    
    void printInfo() {
        Console.print("Person: " + this.name + ", age " + this.age);
    }
}

// ✓ VALID: Typed variables (let <type> name = value)
let int count = 42;
let float price = 19.99;
let string message = "Hello";
let boolean isValid = true;
let int[] numbers = [1, 2, 3, 4, 5];
let string[] names = ["Alice", "Bob"];
let object user = { "name": "John", "age": 30 };

// ============================================
// ERROR DEMONSTRATION (uncomment to see errors):
// ============================================

// ❌ MISSING return type on function
// function badAdd(int a, int b) { return a + b; }

// ❌ MISSING parameter types
// int function badGreet(name) { return "Hi " + name; }

// ❌ MISSING return type AND parameter types
// function terrible(a, b) { return a + b; }

// ❌ UNTYPED variable declaration (strict mode)
// let untyped = 42;

// ❌ UNTYPED array
// let badArray = [1, 2, 3];

// ❌ MISSING return type on constructor
// class BadClass {
//     BadClass() {}
// }

// ❌ UNTYPED class field
// class BadClass2 {
//     name;  // missing type
// }

// ❌ UNTYPED method parameter
// class BadClass3 {
//     void method(param) {}  // param missing type
// }

// ============================================

int function runDemo() {
    Console.print("=== Strict Typing Demo ===\n");
    
    Console.print("add(5, 3) = " + add(5, 3));
    Console.print("greet('World') = " + greet("World"));
    Console.print("calculateArea(4.5, 2.0) = " + calculateArea(4.5, 2.0));
    
    let Person person = new Person("Alice", 25);
    person.printInfo();
    
    Console.print("\nTyped variables:");
    Console.print("count: " + count);
    Console.print("price: " + price);
    Console.print("message: " + message);
    Console.print("isValid: " + isValid);
    Console.print("numbers: " + numbers);
    Console.print("names: " + names);
    Console.print("user: " + user);
    
    Console.print("\n✓ All strict typing checks passed!");
    return 0;
}

runDemo();