integer function maxSubarray(integer[] numbers) {
    if (numbers.length == 0) {
        return 0;
    }

    let integer best = numbers[0];
    let integer running = numbers[0];

    for (let index = 1; index < numbers.length; index++) {
        running = (running > 0 ? running : 0) + numbers[index];
        best = running > best ? running : best;
    }

    return best;
}

function main() {
    print("Maximum subarray:", maxSubarray([-2, 1, -3, 4, -1, 2, 1, -5, 4]));
}
