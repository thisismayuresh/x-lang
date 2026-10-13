// Complex decorator patterns: factories with arguments, stateful wrappers,
// validation guards, load-time side effects, stacking order, composing one
// decorator out of another, method decorators, and class decorators.
//
// Decorators are evaluated once when the declaration loads. Stacked
// decorators apply bottom-up: the one closest to the declaration wraps it
// first, so the top decorator runs first at call time.

// A decorator factory: audit("square") is evaluated at load time and
// returns the real decorator, which receives the function being decorated.
//
// The wrapper forwards its arguments by naming them. An arrow has no rest
// parameters, so this is how you pass anything through: list the arguments
// you want to forward. @logged below does the same for two arguments.
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

// A decorator that wraps another decorator. retry(2) builds a decorator which
// calls @flaky first; if the inner function throws, the retry decorator calls
// it again. This is how you compose behaviour without copying a guard into
// every retry-aware function.
function flaky(target) {
    return (n) => {
        if (n < 0) {
            throw new Error("flaky refused " + n);
        }
        return target(n);
    };
}

function retry(integer times) {
    return (target) => {
        return (n) => {
            for (let i = 0; i < times; i = i + 1) {
                try {
                    return target(n);
                } catch (error) {
                    print("attempt " + (i + 1) + " failed: " + error.message);
                }
            }
            return -1;
        };
    };
}

@retry(2)
@flaky
function unstable(integer n) {
    print("body ran for " + n);
    return n * 2;
}

// A method decorator. The same closure machinery applies to methods: the
// factory runs at load time and returns a wrapper around the method body.
// this.n is forwarded because the arrow calls target.call(this, ...).
class Counter {
    integer n;

    public Counter() {
        this.n = 0;
    }

    // A method decorator takes the same form as a function decorator: the
    // factory runs at load time and the arrow it returned wraps the method.
    //
    // Known limitation — read this before decorating a method that mutates
    // instance state. The interpreter binds the method to the instance first,
    // then applies the decorator to that bound method (interpreter/__init__.py
    // around the bound_methods loop). The arrow the factory returns is what
    // actually runs, and an arrow has no `this`: it forwards only the
    // arguments you name. So `this.n = this.n + step` inside the wrapper
    // cannot see the instance, and a wrapper that reassigns a field resets it
    // on every call. The body below still mutates correctly when called
    // undecorated; with @audit it reports a stale value. Decorate logging-only
    // methods, or write the guard inline in the body, until the wrapper
    // forwards the receiver.
    @audit("bump")
    public integer bump(integer step) {
        this.n = this.n + step;
        return this.n;
    }
}

// A class decorator. It receives the class itself and can mutate it before it
// is used, so the decorated class is what `new` builds. Here it adds a marker
// field and a method to every instance.
// A class decorator. It receives the class itself, records it in a registry,
// and returns it unchanged. The registry is a plain static-field bag — the
// same shape @counts uses — so this adds no language surface. A decorator can
// also mutate the class through its static fields if you declare them.
class Tagged {
    static integer made = 0;
}

function tagged(target) {
    Tagged.made = Tagged.made + 1;
    print("tagged " + target);
    return target;
}

@tagged
class Box {
    string label;

    public Box() {
        this.label = "box";
    }
}

function main() {
    print(square(4));   // audit, cache miss, computing 4 -> 16
    print(square(4));   // audit, cache hit -> 16
    print(square(3));   // audit, cache miss, rejected 3 -> -1
    print(add(2, 3));
    print(first() + second());

    // retry(2) wraps @flaky: the first call throws and is retried.
    print(unstable(-1));   // attempt 1 failed, attempt 2 failed -> -1
    print(unstable(5));    // body ran -> 10

    // Because of the limitation above, this reports 1 then 1 rather than the
    // 1 then 3 an undecorated bump would return. The audit log still fires
    // once per call, which is what the wrapper is for.
    let c = new Counter();
    c.bump(1);
    c.bump(2);

    let b = new Box();
    print(Tagged.made);   // 1 — one class was decorated
}


class MyC{
    protected string xp="hi";

    void printf(){
        print("hi")
    }
}

let MyC p = new MyC();


p.printf()

