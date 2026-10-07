integer function binarySearch(integer[] numbers, integer target) {
    let integer[] steps = [];
    let integer step = 1;
    while (step < numbers.length) {
        steps.add(step);
        step *= 2;
    }

    let integer candidate = -1;
    let integer cursor = steps.length - 1;
    let integer probe = 0;
    while (cursor >= 0) {
        step = steps[cursor];
        probe = candidate + step;
        if (probe < numbers.length && numbers[probe] < target) {
            candidate = probe;
        }
        cursor--;
    }

    let integer found = candidate + 1;
    return found < numbers.length && numbers[found] == target ? found : -1;
}

any function main() {
    print("Binary search index:", binarySearch([-1, 0, 3, 5, 9, 12], 9));
    print("Missing target:", binarySearch([-1, 0, 3, 5, 9, 12], 2));
}
