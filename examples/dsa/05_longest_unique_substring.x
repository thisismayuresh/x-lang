integer function longestUniqueSubstring(string text) {
    let object lastSeen = {};
    let integer start = 0;
    let integer longest = 0;
    let string key = "";
    let integer windowLength = 0;

    for (let index = 0; index < text.length; index++) {
        key = text[index];
        if (Object.hasOwn(lastSeen, key) && lastSeen[key] >= start) {
            start = lastSeen[key] + 1;
        }

        lastSeen[key] = index;
        windowLength = index - start + 1;
        longest = windowLength > longest ? windowLength : longest;
    }

    return longest;
}

function main() {
    print("Longest substring without repeats:");
    print(longestUniqueSubstring("abcabcbb"));
    print(longestUniqueSubstring("bbbbb"));
    print(longestUniqueSubstring("pwwkew"));
}
