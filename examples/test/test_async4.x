async function fetchData(name) {
    await sleep(50)
    return "data for " + name
}

async function main() {
    let result = await fetchData("test")
    print(result)
}