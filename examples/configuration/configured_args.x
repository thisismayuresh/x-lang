function main(string[] args) {
    print("Argument count: " + args.length)
    for (string argument of args) {
        print("Argument: " + argument)
    }
    print("Configured project: " + System.Environment.X_PROJECT)
    print("Selected mode: " + System.Environment.X_MODE)
}
