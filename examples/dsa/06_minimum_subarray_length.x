integer function minSubarrayLength(integer target, integer[] numbers) {
    let integer start = 0;
    let integer total = 0;
    let integer shortest = numbers.length + 1;
    let integer windowLength = 0;

    for (let end = 0; end < numbers.length; end++) {
        total += numbers[end];

        while (total >= target) {
            windowLength = end - start + 1;
            shortest = windowLength < shortest ? windowLength : shortest;
            total -= numbers[start];
            start++;
        }
    }

    return shortest == numbers.length + 1 ? 0 : shortest;
}

function main() {
    print("Minimum positive-sum window:", minSubarrayLength(7, [2, 3, 1, 2, 4, 3]));
}
