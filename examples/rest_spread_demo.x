integer function sum(integer ...numbers) {
    let integer total = 0;
    for (integer number in numbers) {
        total += number;
    }
    return total;
}

function main() {
    let integer[] first = [1, 2, 3];
    let integer[] allNumbers = [0, ...first, 4];
    print("Combined sum: " + sum(...allNumbers));

    let object defaults = {
        name: "Ada",
        role: "Engineer"
    };
    let object profile = {
        ...defaults,
        role: "Architect"
    };
    print(profile.name + " is an " + profile.role);
}
