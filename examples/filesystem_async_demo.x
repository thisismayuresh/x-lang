import System.io.FileSystem

async any function main() {
    let string directory = "build/filesystem-async-demo";
    let string filePath = directory + "/notes.txt";

    FileSystem.createDirectory(directory);
    FileSystem.writeText(filePath, "Written synchronously.\n");
    await FileSystem.appendTextAsync(filePath, "Appended asynchronously.\n");

    let string contents = await FileSystem.readTextAsync(filePath);
    print(contents);
    print("Exists: " + FileSystem.exists(filePath));

    await sleep(100);
    print("Finished after an asynchronous 100 ms sleep.");
}
