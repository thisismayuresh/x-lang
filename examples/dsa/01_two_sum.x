any function twoSum(integer[] numbers, integer target) {
    let object seen = {};
    let integer complement = 0;
    let string key = "";

    for (let index = 0; index < numbers.length; index++) {
        complement = target - numbers[index];
        key = complement.toString();

        if (Object.hasOwn(seen, key)) {
            print("indices:", seen[key], index);
            return;
        }

        seen[numbers[index].toString()] = index;
    }
}

any function main() {
    print("Two Sum");
    twoSum([2, 7, 11, 15], 9);
}
