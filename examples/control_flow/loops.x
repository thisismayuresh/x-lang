function main() {
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
}
