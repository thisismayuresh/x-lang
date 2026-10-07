async function fetchData(name) {
    await sleep(50)
    return "data for " + name
}

async function main() {
    let r1 = await fetchData("item 1")
    let r2 = await fetchData("item 2")
    let r3 = await fetchData("item 3")
    print(r1, r2, r3)
}