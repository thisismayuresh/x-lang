boolean function isValidParentheses(string text) {
    let string[] stack = [];
    let integer top = 0;
    let string token = "";
    let string opening = "";

    for (let index = 0; index < text.length; index++) {
        token = text[index];
        if (token == "(" || token == "[" || token == "{") {
            if (top == stack.length) {
                stack.add(token);
            } else {
                stack[top] = token;
            }
            top++;
        } else {
            if (top == 0) {
                return false;
            }

            top--;
            opening = stack[top];
            if (
                (token == ")" && opening != "(") ||
                (token == "]" && opening != "[") ||
                (token == "}" && opening != "{")
            ) {
                return false;
            }
        }
    }

    return top == 0;
}

any function main() {
    print("Balanced brackets:", isValidParentheses("{[()]}"));
    print("Unbalanced brackets:", isValidParentheses("([)]"));
}
