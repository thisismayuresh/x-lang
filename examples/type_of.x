any function main() {
    let object profile = {
        "name": "Maya",
        age: 21
    };

    print(typeOf(profile)); // object
    print(typeOf(profile.name)); // string
    print(typeOf(profile.age)); // number
    print(typeOf(null)); // object, matching JavaScript typeof

    let object<string, string> user = {
        "name": "Maya",
        "age": "21",
        "gender": "Rather not to say"
    };

    print(typeOf(user)); // object
}
