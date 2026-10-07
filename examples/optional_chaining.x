string function getName(string name) {
    return name;
}

any function main() {
    let users = ["Alice", "Bob"];
    let profile = [{name: "Maya"}];
    let missing = null;
    let callback = null;

    print(users?[0]);
    print(typeOf(users?[5]));
    print(profile?[0]?.name);
    print(typeOf(missing?.profile?.name));
    print(typeOf(missing?.getName?.()));
    print(getName?.("Grace"));
    print(callback?.());

    let message = true ? users?[1] : "no user";
    print(message);
}
