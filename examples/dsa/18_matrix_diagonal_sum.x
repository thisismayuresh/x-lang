integer function diagonalSum(integer[][] matrix) {
    let integer total = 0;
    let integer size = matrix.length;
    let integer opposite = 0;

    for (let index = 0; index < size; index++) {
        total += matrix[index][index];
        opposite = size - 1 - index;
        if (opposite != index) {
            total += matrix[index][opposite];
        }
    }

    return total;
}

function main() {
    let integer[][] matrix = [
        [1, 2, 3],
        [4, 5, 6],
        [7, 8, 9]
    ];
    print("Matrix diagonal sum:", diagonalSum(matrix));
}
