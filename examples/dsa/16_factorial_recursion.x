integer function factorial(integer number) {
    if (number < 0) {
        return 0;
    }
    if (number < 2) {
        return 1;
    }
    return number * factorial(number - 1);
}

any function main() {
    print("Factorial:", factorial(6));
}
