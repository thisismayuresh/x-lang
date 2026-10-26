// Verhoeff-algorithm Aadhaar generator, transpiled from the JS original.
// A candidate is twelve random digits, rejected until the Verhoeff
// checksum validates (plus the trivial all-same-digit rejection).

import System.utils.Math

const integer[][] VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
];

const integer[][] VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]
];

boolean function isValidAadhar(string aadhar) {
    // /^\d{12}$/ — exactly twelve ASCII digits.
    if (aadhar.length != 12) {
        return false;
    }
    for (let i = 0; i < 12; i = i + 1) {
        let integer code = aadhar.charAt(i).codePointAt(0);
        if (code < 48 || code > 57) {
            return false;
        }
    }

    // /^(\d)\1{11}$/ — all twelve digits identical.
    let string first = aadhar.charAt(0);
    if (aadhar.replaceAll(first, "").isEmpty()) {
        return false;
    }

    // Verhoeff checksum, consuming the digits from the right.
    let integer c = 0;
    for (let i = 0; i < 12; i = i + 1) {
        let integer digit = aadhar.charAt(11 - i).codePointAt(0) - 48;
        c = VERHOEFF_D[c][VERHOEFF_P[i % 8][digit]];
    }
    return c == 0;
}

export string function getValidAadhar() {
    let string aadhar = "";
    do {
        aadhar = "";
        for (let i = 0; i < 12; i = i + 1) {
            aadhar = aadhar + Math.floor(Math.random() * 10);
        }
    } while (!isValidAadhar(aadhar));
    return aadhar;
}
