any function main() {
    try {
        throw new Exception("planned failure")
    }
    catch (RuntimeException | Exception error) {
        print(error.name + ": " + error.message)
    }
    finally {
        print("cleanup always runs")
    }
}
