import System.io.Console
import System.io.FileSystem
import System.utils.Math
import System.utils.Collections.HashMap
import System.utils.Collections.LinkedList
import System.utils.Collections.Stack
import System.utils.Collections.Queue

// ============================================
// DECORATOR EXAMPLES
// ============================================

// The @trace decorator is built-in
@trace
function add(a, b) {
    return a + b;
}

// Using @trace for caching
@trace
function fibonacci(n) {
    if (n <= 1) return n;
    return fibonacci(n - 1) + fibonacci(n - 2);
}

// Using @trace for measuring execution
@trace
function slowOp(n) {
    let sum = 0;
    for (let i = 0; i < n; i = i + 1) {
        sum = sum + i;
    }
    return sum;
}

// Using @trace for argument validation
@trace
function divide(a, b) {
    if (b == 0) throw "Division by zero";
    return a / b;
}

// Using @trace for retry logic
@trace
function flaky(shouldFail) {
    if (shouldFail) throw "Random failure";
    return "Success";
}

// ============================================
// TYPE SYSTEM TESTS
// ============================================

// Primitive types - inferred
let age = 25;
let height = 5.9;
let name = "John";
let isActive = true;

// Explicit type declarations (strict mode would require these)
let int age2 = 25;
let float height2 = 5.9;
let string name2 = "John";
let boolean isActive2 = true;

// Array types
let int[] numbers = [1, 2, 3, 4, 5];
let string[] names = ["Alice", "Bob", "Charlie"];
let float[] scores = [95.5, 87.2, 91.0];

// Nested arrays
let int[][] matrix = [
    [1, 2, 3],
    [4, 5, 6],
    [7, 8, 9]
];

// Object types
let object person = {
    "name": "John",
    "age": 30,
    "city": "New York"
};

// ============================================
// FUNCTION TESTS
// ============================================

function calculateArea(int width, int height) {
    return width * height;
}

function greet(string name, string greeting = "Hello") {
    return greeting + ", " + name + "!";
}

function sum(int... numbers) {
    let total = 0;
    for (let n of numbers) {
        total = total + n;
    }
    return total;
}

// Arrow functions (using regular function instead)

// Higher-order functions (simplified)
function applyOperation(int a, int b, int opType) {
    if (opType == 0) return a + b;
    if (opType == 1) return a - b;
    if (opType == 2) return a * b;
    return a / b;
}

// Async functions
async function fetchData(string url) {
    await sleep(10);
    return "Data from " + url;
}

async function processData() {
    let result = await fetchData("https://api.example.com");
    return "Processed: " + result;
}

// ============================================
// CLASS TESTS
// ============================================

class Animal {
    string name;
    int age;

    Animal(string name, int age) {
        this.name = name;
        this.age = age;
    }

    void makeSound() {
        Console.print(this.name + " makes a sound");
    }

    string getName() {
        return this.name;
    }

    int getAge() {
        return this.age;
    }
}

class Dog extends Animal {
    string breed;

    Dog(string name, int age, string breed) {
        super(name, age);
        this.breed = breed;
    }

    void makeSound() {
        Console.print(this.name + " barks!");
    }

    string getBreed() {
        return this.breed;
    }
}

class Cat extends Animal {
    boolean isIndoor;

    Cat(string name, int age, boolean isIndoor) {
        super(name, age);
        this.isIndoor = isIndoor;
    }

    void makeSound() {
        Console.print(this.name + " meows!");
    }
}

// Abstract class
abstract class Shape {
    string color;

    Shape(string color) {
        this.color = color;
    }

    abstract float getArea();

    string getColor() {
        return this.color;
    }
}

class Circle extends Shape {
    float radius;

    Circle(string color, float radius) {
        super(color);
        this.radius = radius;
    }

    float getArea() {
        return Math.pi * this.radius * this.radius;
    }
}

class Rectangle extends Shape {
    float width;
    float height;

    Rectangle(string color, float width, float height) {
        super(color);
        this.width = width;
        this.height = height;
    }

    float getArea() {
        return this.width * this.height;
    }
}

// ============================================
// INTERFACE TESTS
// ============================================

interface Drawable {
    void draw();
    string getDescription();
}

interface Serializable {
    string serialize();
    void deserialize(string data);
}

class DrawableCircle extends Circle implements Drawable, Serializable {
    DrawableCircle(string color, float radius) {
        super(color, radius);
    }

    void draw() {
        Console.print("Drawing circle with radius " + this.radius);
    }

    string getDescription() {
        return "Circle(radius=" + this.radius + ")";
    }

    string serialize() {
        return "Circle|" + this.color + "|" + this.radius;
    }

    void deserialize(string data) {
        let parts = data.split("|");
        this.color = parts[1];
        this.radius = 0 + parts[2];
    }
}

// ============================================
// ENUM TESTS
// ============================================

enum Color {
    RED = 1,
    GREEN = 2,
    BLUE = 3,
    YELLOW = 4
}

enum Status {
    PENDING = "pending",
    ACTIVE = "active",
    COMPLETED = "completed",
    FAILED = "failed"
}

enum Direction {
    NORTH,
    SOUTH,
    EAST,
    WEST
}

// ============================================
// COLLECTION TESTS
// ============================================

// LinkedList
let LinkedList stringList = LinkedList.create();
stringList.add("first");
stringList.add("second");
stringList.add("third");

// HashMap
let HashMap userMap = HashMap.create();
userMap.set("user1", { "name": "Alice", "age": 25 });
userMap.set("user2", { "name": "Bob", "age": 30 });
userMap.set("user3", { "name": "Charlie", "age": 35 });

// Stack
let Stack intStack = Stack.create();
intStack.push(1);
intStack.push(2);
intStack.push(3);

// Queue
let Queue stringQueue = Queue.create();
stringQueue.enqueue("first");
stringQueue.enqueue("second");
stringQueue.enqueue("third");

// ============================================
// PATTERN MATCHING TESTS
// ============================================

function describeValue(value) {
    match (value) {
        null => "Null",
        undefined => "Undefined",
        42 => "Integer: 42",
        3.14 => "Float: 3.14",
        "hello" => "String: hello",
        true => "Boolean: true",
        [1, 2, 3] => "Int array of length 3",
        ["a", "b"] => "String array of length 2",
        _ => "Unknown type"
    }
}

// ============================================
// DESTRUCTURING TESTS
// ============================================

let int[] coords = [10, 20];
let int x = coords[0];
let int y = coords[1];

let object user = { "name": "John", "age": 30, "city": "NYC" };
let string userName = user.name;
let int userAge = user.age;

function getUser() {
    return { "name": "Jane", "age": 25, "email": "jane@example.com" };
}

let userObj = getUser();
let n = userObj.name;
let a = userObj.age;

// ============================================
// SPREAD OPERATOR TESTS
// ============================================

let int[] arr1 = [1, 2, 3];
let int[] arr2 = [...arr1, 4, 5, 6];

let object obj1 = { "a": 1, "b": 2 };
let object obj2 = { ...obj1, "c": 3 };

function combineArrays(int[][] arrays) {
    let result = [];
    for (let arr of arrays) {
        result = [...result, ...arr];
    }
    return result;
}

// ============================================
// EXCEPTION HANDLING TESTS
// ============================================

class CustomException extends Exception {
    CustomException(string message) {
        super(message);
    }
}

function riskyOperation(boolean shouldFail) {
    if (shouldFail) {
        throw new CustomException("Operation failed!");
    }
    return "Success";
}

function handleErrors() {
    try {
        let result = riskyOperation(true);
        Console.print("Result: " + result);
    } catch (CustomException e) {
        Console.print("Caught CustomException: " + e.message);
    } catch (Exception e) {
        Console.print("Caught generic Exception: " + e.message);
    } finally {
        Console.print("Finally block executed");
    }
}

// ============================================
// FILE SYSTEM TESTS
// ============================================

function fileSystemTests() {
    let testFile = "test_output.txt";
    let content = "Hello, World!\nThis is a test file.\nLine 3.";

    FileSystem.writeText(testFile, content);
    Console.print("File written: " + testFile);

    let readContent = FileSystem.readText(testFile);
    Console.print("File content:\n" + readContent);

    Console.print("File exists: " + FileSystem.exists(testFile));
    Console.print("Is file: " + FileSystem.isFile(testFile));
    Console.print("Is directory: " + FileSystem.isDirectory(testFile));

    let files = FileSystem.listDirectory(".");
    Console.print("Files in current directory:");
    for (let f of files) {
        Console.print("  - " + f);
    }

    FileSystem.deleteFile(testFile);
    Console.print("File deleted: " + testFile);
}

// ============================================
// MATH TESTS
// ============================================

function mathTests() {
    Console.print("PI: " + Math.pi);
    Console.print("E: " + Math.e);
    Console.print("sqrt(16): " + Math.sqrt(16));
    Console.print("pow(2, 10): " + Math.pow(2, 10));
    Console.print("sin(PI/2): " + Math.sin(Math.pi / 2));
    Console.print("cos(0): " + Math.cos(0));
    Console.print("log(10): " + Math.log(10));
    Console.print("floor(3.7): " + Math.floor(3.7));
    Console.print("ceil(3.2): " + Math.ceil(3.2));
    Console.print("round(3.5): " + Math.round(3.5));
    Console.print("abs(-5): " + Math.abs(-5));
    Console.print("min(1, 5, 3): " + Math.min(1, 5, 3));
    Console.print("max(1, 5, 3): " + Math.max(1, 5, 3));
    Console.print("random(): " + Math.random());
}

// ============================================
// SWITCH TESTS
// ============================================

function testSwitch(value) {
    switch (value) {
        case 1: {
            Console.print("One")
        }
        case 2: {
            Console.print("Two")
        }
        case 3: {
            Console.print("Three")
        }
        default: {
            Console.print("Other: " + value)
        }
    }
}

function testNestedSwitch(x, y) {
    switch (x) {
        case 1: {
            Console.print("x is 1")
            switch (y) {
                case 10: {
                    Console.print("  y is 10")
                }
                case 20: {
                    Console.print("  y is 20")
                }
                default: {
                    Console.print("  y is other: " + y)
                }
            }
        }
        case 2: {
            Console.print("x is 2")
        }
        default: {
            Console.print("x is other: " + x)
        }
    }
}

// ============================================
// MAIN TEST RUNNER
// ============================================

function runAllTests() {
    Console.print("============================================");
    Console.print("RUNNING COMPREHENSIVE TESTS");
    Console.print("============================================\n");

    // Decorator tests
    Console.print("--- Decorator Tests ---");
    Console.print("add(2, 3) = " + add(2, 3));
    Console.print("fibonacci(10) = " + fibonacci(10));
    Console.print("slowOp(100000) = " + slowOp(100000));
    Console.print("divide(10, 2) = " + divide(10, 2));

    try {
        flaky(false);
    } catch (e) {
        Console.print("Retry test (should fail): " + e);
    }

    // Type tests
    Console.print("\n--- Type System Tests ---");
    Console.print("age: " + age + " (type: " + typeOf(age) + ")");
    Console.print("height: " + height + " (type: " + typeOf(height) + ")");
    Console.print("name: " + name + " (type: " + typeOf(name) + ")");
    Console.print("isActive: " + isActive + " (type: " + typeOf(isActive) + ")");
    Console.print("numbers: " + numbers);
    Console.print("matrix: " + matrix);
    Console.print("person: " + person);

    // Function tests
    Console.print("\n--- Function Tests ---");
    Console.print("calculateArea(5, 3) = " + calculateArea(5, 3));
    Console.print("greet('World') = " + greet("World"));
    Console.print("greet('World', 'Hi') = " + greet("World", "Hi"));
    Console.print("sum(1, 2, 3, 4, 5) = " + sum(1, 2, 3, 4, 5));
    Console.print("multiply(4, 5) = " + multiply(4, 5));
    Console.print("square(6) = " + square(6));
    Console.print("applyOperation(10, 5, 2) = " + applyOperation(10, 5, 2));

    // Class tests
    Console.print("\n--- Class Tests ---");
    let dog = new Dog("Buddy", 3, "Golden Retriever");
    let cat = new Cat("Whiskers", 2, true);
    dog.makeSound();
    cat.makeSound();
    Console.print("Dog: " + dog.getName() + ", " + dog.getAge() + ", " + dog.getBreed());
    Console.print("Cat: " + cat.getName() + ", " + cat.getAge());

    // Shape tests
    let circle = new Circle("red", 5.0);
    let rectangle = new Rectangle("blue", 4.0, 6.0);
    Console.print("Circle area: " + circle.getArea() + ", color: " + circle.getColor());
    Console.print("Rectangle area: " + rectangle.getArea() + ", color: " + rectangle.getColor());

    // Interface tests
    Console.print("\n--- Interface Tests ---");
    let drawableCircle = new DrawableCircle("green", 3.0);
    drawableCircle.draw();
    Console.print("Description: " + drawableCircle.getDescription());
    let serialized = drawableCircle.serialize();
    Console.print("Serialized: " + serialized);
    let newCircle = new DrawableCircle("", 0);
    newCircle.deserialize(serialized);
    Console.print("Deserialized: " + newCircle.getDescription());

    // Enum tests
    Console.print("\n--- Enum Tests ---");
    Console.print("Color.RED: " + Color.RED);
    Console.print("Status.ACTIVE: " + Status.ACTIVE);
    Console.print("Direction.NORTH: " + Direction.NORTH);

    // Collection tests
    Console.print("\n--- Collection Tests ---");
    Console.print("stringList: " + stringList);
    Console.print("userMap: " + userMap);
    Console.print("intStack: " + intStack);
    Console.print("stringQueue: " + stringQueue);

    // Pattern matching
    Console.print("\n--- Pattern Matching ---");
    Console.print(describeValue(42));
    Console.print(describeValue(3.14));
    Console.print(describeValue("hello"));
    Console.print(describeValue(true));
    Console.print(describeValue(null));
    Console.print(describeValue([1, 2, 3]));
    Console.print(describeValue({ "name": "Test", "age": 25 }));

    // Destructuring
    Console.print("\n--- Destructuring ---");
    Console.print("x: " + x + ", y: " + y);
    Console.print("userName: " + userName + ", userAge: " + userAge);
    Console.print("n: " + n + ", a: " + a);

    // Spread operator
    Console.print("\n--- Spread Operator ---");
    Console.print("arr2: " + arr2);
    Console.print("obj2: " + obj2);
    Console.print("combineArrays: " + combineArrays([[1,2], [3,4], [5]]));

    // Exception handling
    Console.print("\n--- Exception Handling ---");
    handleErrors();

    // File system
    Console.print("\n--- File System Tests ---");
    fileSystemTests();

    // Math
    Console.print("\n--- Math Tests ---");
    mathTests();

    // Switch tests
    Console.print("\n--- Switch Tests ---");
    testSwitch(1);
    testSwitch(2);
    testSwitch(3);
    testSwitch(5);

    testNestedSwitch(1, 10);
    testNestedSwitch(1, 20);
    testNestedSwitch(1, 30);
    testNestedSwitch(2, 10);
    testNestedSwitch(3, 10);

    Console.print("\n============================================");
    Console.print("ALL TESTS COMPLETED SUCCESSFULLY");
    Console.print("============================================");
}

// ============================================
// FUNCTION DEFINITIONS (moved to bottom for readability)
// ============================================

// Strict typing demo - uncomment and run with strict_typing=true to see errors:
// function badAdd(a, b) { return a + b; }  // Missing return type and parameter types

function multiply(int a, int b) {
    return a * b;
}

function square(int x) {
    return x * x;
}

function riskyOperation(boolean shouldFail) {
    if (shouldFail) {
        throw new CustomException("Operation failed!");
    }
    return "Success";
}


            switch (y) {
                case 10: {
                    Console.print("  y is 10")
                }
                case 20: {
                    Console.print("  y is 20")
                }
                default: {
                    Console.print("  y is other: " + y)
                }
       
        }


// ============================================
// ENTRY POINT
// ============================================

runAllTests();