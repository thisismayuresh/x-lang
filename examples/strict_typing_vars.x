// ============================================
// STRICT TYPING - VARIABLE ERRORS
// ============================================
// Run with: python -m xlang examples/strict_typing_vars.x --strict_typing=true
// ============================================

// Error: Untyped variable declaration
let untyped = 42;

// Error: Untyped array
let badArray = [1, 2, 3];

int function main() { return 0; }