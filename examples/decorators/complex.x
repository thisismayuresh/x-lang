// Complex decorator patterns: factories with arguments, stateful wrappers,
// validation guards, load-time side effects, and stacking order.
//
// Decorators are evaluated once when the declaration loads. Stacked
// decorators apply bottom-up: the one closest to the declaration wraps it
// first, so the top decorator runs first at call time.

// A decorator factory: audit("square") is evaluated at load time and
// returns the real decorator, which receives the function being decorated.
function audit(string label) {
    return (target) => (n) => {
        print("[audit] " + label + " -> " + n);
        return target(n);
    };
}

// A stateful wrapper. The cache lives in the closure created when the
// decorator runs, so every decorated function gets its own cache.
function memoize(var target) {
    let cache = {};
    return (n) => {
        if (n in cache) {
            print("cache hit " + n);
            return cache[n];
        }
        print("cache miss " + n);
        let result = target(n);
        cache[n] = result;
        return result;
    };
}

// A guard: rejects inputs before the function body ever runs.
function requireEven(var target) {
    return (n) => {
        if (n % 2 != 0) {
            print("rejected " + n);
            return -1;
        }
        return target(n);
    };
}

// Wrapping a multi-argument function: return an arrow that forwards every
// argument to the original.
function logged(var target) {
    return (a, b) => {
        print("adding " + a + " + " + b);
        return target(a, b);
    };
}

// Load-time side effects. This decorator is not a factory: it runs once
// while the declaration loads, mutates class state, and returns the
// function unchanged. Stacking @counts on several declarations counts
// every registration.
class Registry {
    static integer count = 0;
}

function counts(var target) {
    Registry.count = Registry.count + 1;
    print("registered " + Registry.count);
    return target;
}

// Stacking: application order is requireEven -> memoize -> audit, so a
// call runs audit first, then the cache check, then the guard, then the
// body.
@audit("square")
@memoize
@requireEven
function square(integer n) {
    print("computing " + n);
    return n * n;
}

@counts
function first() {
    return 1;
}

@counts
function second() {
    return 2;
}

@logged
function add(integer a, integer b) {
    return a + b;
}

function main() {
    print(square(4));   // audit, cache miss, computing 4 -> 16
    print(square(4));   // audit, cache hit -> 16
    print(square(3));   // audit, cache miss, rejected 3 -> -1
    print(add(2, 3));
    print(first() + second());
}
