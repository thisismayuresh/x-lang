async function fetchData(name) {
    await sleep(50)
    return "data for " + name
}

async function main() {
    let results = []
    for (let i = 0; i < 3; i = i + 1) {
        let r = await fetchData("item " + i)
        results.push(r)
    }
    print(results)
}