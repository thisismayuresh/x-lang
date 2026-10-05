function fillRegion(integer[][] image, integer row, integer column, integer original, integer replacement) {
    if (
        row < 0 ||
        row >= image.length ||
        column < 0 ||
        column >= image[row].length ||
        image[row][column] != original
    ) {
        return;
    }

    image[row][column] = replacement;
    fillRegion(image, row - 1, column, original, replacement);
    fillRegion(image, row + 1, column, original, replacement);
    fillRegion(image, row, column - 1, original, replacement);
    fillRegion(image, row, column + 1, original, replacement);
}

function floodFill(integer[][] image, integer startRow, integer startColumn, integer color) {
    let integer original = image[startRow][startColumn];
    if (original != color) {
        fillRegion(image, startRow, startColumn, original, color);
    }
}

function main() {
    let integer[][] image = [
        [1, 1, 1],
        [1, 1, 0],
        [1, 0, 1]
    ];
    floodFill(image, 1, 1, 2);
    print("Flood-filled image:", image);
}
