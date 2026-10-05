integer function removeDuplicates(integer[] numbers) {
    if (numbers.length == 0) {
        return 0;
    }

    let integer write = 1;
    for (let read = 1; read < numbers.length; read++) {
        if (numbers[read] != numbers[write - 1]) {
            numbers[write] = numbers[read];
            write++;
        }
    }

    return write;
}

function main() {
    let integer[] numbers = [0, 0, 1, 1, 1, 2, 2, 3, 3, 4];
    let integer uniqueCount = removeDuplicates(numbers);
    print("Unique count:", uniqueCount);
    for (let index = 0; index < uniqueCount; index++) {
        print(numbers[index]);
    }
}
