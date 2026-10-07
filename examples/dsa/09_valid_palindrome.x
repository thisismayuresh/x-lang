boolean function isPalindrome(string text) {
    let integer left = 0;
    let integer right = text.length - 1;

    while (left < right) {
        if (text[left] != text[right]) {
            return false;
        }
        left++;
        right--;
    }

    return true;
}

any function main() {
    print("Palindrome checks:", isPalindrome("racecar"), isPalindrome("x-language"));
}
