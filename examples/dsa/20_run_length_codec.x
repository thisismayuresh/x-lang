boolean function isDigit(string character) {
    return character >= "0" && character <= "9";
}

integer function digitValue(string character) {
    if (character == "0") return 0;
    if (character == "1") return 1;
    if (character == "2") return 2;
    if (character == "3") return 3;
    if (character == "4") return 4;
    if (character == "5") return 5;
    if (character == "6") return 6;
    if (character == "7") return 7;
    if (character == "8") return 8;
    if (character == "9") return 9;
    return -1;
}

string function encodeRuns(string text) {
    if (text.length == 0) {
        return "";
    }

    let string encoded = "";
    let integer runLength = 1;

    for (let index = 1; index <= text.length; index++) {
        if (index < text.length && text[index] == text[index - 1]) {
            runLength++;
        } else {
            encoded += text[index - 1];
            if (runLength > 1) {
                encoded += runLength.toString();
            }
            runLength = 1;
        }
    }

    return encoded;
}

string function decodeRuns(string encoded) {
    let string decoded = "";
    let integer index = 0;
    let string character = "";
    let integer count = 0;

    while (index < encoded.length) {
        character = encoded[index];
        index++;

        count = 0;
        while (index < encoded.length && isDigit(encoded[index])) {
            count = count * 10 + digitValue(encoded[index]);
            index++;
        }
        if (count == 0) {
            count = 1;
        }

        for (let repeat = 0; repeat < count; repeat++) {
            decoded += character;
        }
    }

    return decoded;
}

any function main() {
    let string original = "aaab";
    let string encoded = encodeRuns(original);
    print("Run-length encode:", original, "->", encoded);
    print("Run-length decode:", encoded, "->", decodeRuns(encoded));
}
