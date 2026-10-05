function moveZeroes(integer[] numbers) {
    let integer nextNonZero = 0;
    let integer value = 0;

    for (let scan = 0; scan < numbers.length; scan++) {
        if (numbers[scan] != 0) {
            value = numbers[nextNonZero];
            numbers[nextNonZero] = numbers[scan];
            numbers[scan] = value;
            nextNonZero++;
        }
    }
}

function main() {
    let integer[] numbers = [0, 1, 0, 3, 12];
    moveZeroes(numbers);
    print("Move zeroes:", numbers);
}
