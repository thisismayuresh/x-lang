any function main() {
    const [first, second = 2, ...remaining] = [1]
    const profile = {
        name: "Ada",
        role: "engineer",
        active: true
    }
    const {name, role: title, ...metadata} = profile

    let left = 0
    let right = 0;
    [left, right] = [3, 4]

    print(first + second)
    print(name + " is an " + title)
    print(metadata.active)
    print("unpacked values: " + left + ", " + right)
    print("rest length: " + remaining.length)
    print("keys: " + Object.keys(profile).length)
}
