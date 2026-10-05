integer[] function mergeSorted(integer[] left, integer[] right) {
    let integer[] merged = [];
    let integer i = 0;
    let integer j = 0;

    while (i < left.length && j < right.length) {
        if (left[i] <= right[j]) {
            merged.add(left[i]);
            i++;
        } else {
            merged.add(right[j]);
            j++;
        }
    }

    while (i < left.length) {
        merged.add(left[i]);
        i++;
    }
    while (j < right.length) {
        merged.add(right[j]);
        j++;
    }

    return merged;
}

function main() {
    print("Merged arrays:", mergeSorted([1, 3, 5], [2, 4, 6]));
}
