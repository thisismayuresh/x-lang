integer function lowerBound(integer[] numbers, integer target) {
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

    return candidate + 1;
}

any function main() {
    let integer[] numbers = [1, 2, 2, 2, 4, 7];
    print("First position of 2:", lowerBound(numbers, 2));
    print("Insertion position of 3:", lowerBound(numbers, 3));
}
