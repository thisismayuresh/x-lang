any function main(string[] args) {
    print("Argument count: " + args.length)
    for (string argument of args) {
        print("Argument: " + argument)
    }
    print("Configured project: " + System.process.Environment.X_PROJECT)
    print("Selected mode: " + System.process.Environment.X_MODE)
    print("Service name: " + System.process.Environment.X_SERVICE_NAME)
    print("API base URL: " + System.process.Environment.X_API_BASE_URL)
    print("Has service name: " + System.process.Environment.has("X_SERVICE_NAME"))
}
