@trace
string function greet(string name) {
    return "Hello, " + name
}

class Greeter {
    public Greeter() {}

    @trace
    public string greet(string name) {
        return "Welcome, " + name
    }
}

any function main() {
    print(greet("Ada"))
    let Greeter greeter = new Greeter()
    print(greeter.greet("Lin"))
}
