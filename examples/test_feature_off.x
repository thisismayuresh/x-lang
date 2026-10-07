import System.io.Console

// Test: Using switch when feature is disabled
// Run with: x --config x.toml --feature switch=off run examples/test_feature_off.x
// Should error: Language feature 'switch' is disabled

switch (1) {
    case 1: {
        Console.print("One")
    }
    default: {
        Console.print("Other")
    }
}