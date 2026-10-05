integer[] function nextGreater(integer[] numbers) {
    let integer[] answer = [];
    let integer[] stack = [];
    let integer top = 0;
    let integer previous = 0;

    for (let index = 0; index < numbers.length; index++) {
        answer.add(-1);
        while (top > 0 && numbers[index] > numbers[stack[top - 1]]) {
            previous = stack[top - 1];
            answer[previous] = numbers[index];
            top--;
        }

        if (top == stack.length) {
            stack.add(index);
        } else {
            stack[top] = index;
        }
        top++;
    }

    return answer;
}

function main() {
    print("Next greater values:", nextGreater([2, 1, 2, 4, 3]));
}
