integer function fibonacci(integer number, object memo) {
    let string key = number.toString();
    if (Object.hasOwn(memo, key)) {
        return memo[key];
    }

    let integer result = fibonacci(number - 1, memo) + fibonacci(number - 2, memo);
    memo[key] = result;
    return result;
}

function main() {
    let object memo = {"0": 0, "1": 1};
    print("Fibonacci:", fibonacci(10, memo));
}
