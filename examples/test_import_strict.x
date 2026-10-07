// ============================================
// MAIN FILE - imports untyped functions
// ============================================
import System.io.Console
import imported_func.untypedImported
import imported_func.typedImported

function mainUntyped(a, b) {
    return a + b;
}

int function mainTyped(int a, int b) {
    return a + b;
}

int function main() {
    Console.print("Testing imported functions:");
    Console.print("untypedImported(1, 2) = " + untypedImported(1, 2));
    Console.print("typedImported(1, 2) = " + typedImported(1, 2));
    Console.print("mainUntyped(1, 2) = " + mainUntyped(1, 2));
    Console.print("mainTyped(1, 2) = " + mainTyped(1, 2));
    return 0;
}

main();