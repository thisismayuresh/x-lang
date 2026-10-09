// import System.utils.Math

function findPair(numbers, target) {
  let left = 0;
  let right = numbers.length - 1;

  while (left < right) {
    let sum = numbers[left] + numbers[right];

    if (sum === target) {
      return [left + 1, right + 1];
    }

    if (sum > target) {
      right--;
    } else {
      left++;
    }
  }

  return [];
}

function main() {
  let numbers = [2, 3, 4];
  let pair = findPair(numbers, 6);
  print(pair);
}
