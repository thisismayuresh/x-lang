async function fetchData() {
    await sleep(100)
    return "data"
}

async function main() {
    let result = await fetchData()
    print(result)
}