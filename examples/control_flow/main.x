// Exported module function invoked by runner.x.
export any function main() {
     enum X {
        YES,
        NO
    }

    enum Y{
        YES,
         NO
    }

    print("Statement", X.YES===Y.YES)

    let X sameEnumMember = X.YES
    let Y otherEnumMember = Y.YES
    print("same enum member=" + (sameEnumMember == X.YES))
    print("different enum=" + (sameEnumMember == otherEnumMember))

    let integer total = 0
    let integer index = 0
    while (index < 2) {
        total += index
        index++
    }

    do {
        total++
    } while (total < 3)

    for (let step = 0; step < 2; step++) {
        total += step
    }

    for (const value of [10, 20]) {
        total += value
    }

    let object labels = {first: "one", second: "two"}
    for (const key in labels) {
        print(key + "=" + labels[key])
    }
    print("total=" + total)


 

        let x = 0
    for (let i in range (1,10)){

        print("Hello "+x, "Hi");

        x++;
    }


}

main()
