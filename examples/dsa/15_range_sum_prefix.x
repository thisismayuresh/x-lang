integer function rangeSum(integer[] numbers, integer left, integer right) {
    let integer[] prefix = [0];
    for (let index = 0; index < numbers.length; index++) {
        prefix.add(prefix[index] + numbers[index]);
    }

    return prefix[right + 1] - prefix[left];
}

any function main() {
    let integer[] numbers = [2, 4, 6, 8, 10];
    print("Sum from index 1 through 3:", rangeSum(numbers, 1, 3));
}
