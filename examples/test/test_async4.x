async any function fetchData(string name) {
    await sleep(50)
    return "data for " + name
}

async any function main() {
    let result = await fetchData("test")
    print(result)
}