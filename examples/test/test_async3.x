async any function fetchData(string name) {
    await sleep(50)
    return "data for " + name
}

async any function main() {
    let results = []
    for (let i = 0; i < 3; i = i + 1) {
        results.push(await fetchData("item " + i))
    }
    print(results)
}