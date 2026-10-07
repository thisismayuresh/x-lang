// ============================================
// STRICT TYPING ERROR EXAMPLES
// ============================================
// Run with: python -m xlang examples/strict_typing_errors.x --strict_typing=true
// ============================================

// Error 1: Missing return type on function
function add(a, b) {
    return a + b;
}

// Error 2: Missing parameter types
int function greet(name) {
    return "Hi " + name;
}

// Error 3: Missing return type AND parameter types
function terrible(a, b) {
    return a + b;
}

// Error 4: Untyped variable declaration
let untyped = 42;

// Error 5: Untyped array
let badArray = [1, 2, 3];

// Error 6: Missing return type on constructor
class BadClass {
    BadClass() {}
}

// Error 7: Untyped class field
class BadClass2 {
    string name;
}

// Error 8: Untyped method parameter
class BadClass3 {
    void method(param) {}
}

int function main() { return 0; }