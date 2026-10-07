integer function maxWater(integer[] heights) {
    let integer left = 0;
    let integer right = heights.length - 1;
    let integer best = 0;
    let integer height = 0;
    let integer area = 0;

    while (left < right) {
        height = heights[left] < heights[right]
            ? heights[left]
            : heights[right];
        area = height * (right - left);
        best = area > best ? area : best;

        if (heights[left] < heights[right]) {
            left++;
        } else {
            right--;
        }
    }

    return best;
}

any function main() {
    print("Container with most water:", maxWater([1, 8, 6, 2, 5, 4, 8, 3, 7]));
}
