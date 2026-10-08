import System.utils.Math

integer[] function findLargestNumberInArray(integer[] array){
    print(array);

    let largestNumber = Math.max(...array);

    let name ="Maya";

    print(`largestNumber, {name.toUpperCase()}, {Math.max(...array)}`)


    for(let i in range(0, array.length)){
        break
        print("Array Of I", array[i]);
    }
    return array
}


findLargestNumberInArray([1,2,3,55,4,5,6]);




