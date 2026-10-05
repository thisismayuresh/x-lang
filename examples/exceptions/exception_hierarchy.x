import System.io.FileSystem

class CustomException extends Exception {
    public integer statusCode;

    public CustomException(string message, integer statusCode) {
        super(message);
        this.statusCode = statusCode;
    }
}

class BadRequestException extends CustomException {
    public BadRequestException(string message) {
        super(message, 400);
    }
}

function main(string[] args) {
    try {
        let integer result = 10 / 0;
    }
    catch (ArithmeticException error) {
        print(error.name + ": " + error.message);
    }
    catch (Throwable error) {
        print("Unexpected failure: " + error.message);
    }

    try {
        throw new BadRequestException("invalid user id");
    }
    catch (CustomException error) {
        print(error.name + ": " + error.message);
        print("HTTP status: " + error.statusCode);
    }

    try {
        throw new DatabaseException(
            "query failed",
            new IOException("connection unavailable")
        );
    }
    catch (Exception error) {
        print(error.name + ": " + error.message);
        print("Cause: " + error.cause.message);
    }

    try {
        FileSystem.readText(args[0]);
    }
    catch (IOException error) {
        print(error.name + ": " + error.message);
    }
    finally {
        print("file operation finished");
    }
}
