async any function fetchData() {
    await sleep(100)
    return "data"
}

async any function main() {
    let result = await fetchData()
    print(result)
}