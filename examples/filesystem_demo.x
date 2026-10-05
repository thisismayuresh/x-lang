import System.io.FileSystem

function main() {
    let string directory = "build/filesystem-demo";
    let string filePath = directory + "/notes.txt";

    FileSystem.createDirectory(directory);
    FileSystem.writeText(filePath, "X can write files.\n");
    FileSystem.appendText(filePath, "This line was appended.\n");

    print("Directory exists: " + FileSystem.isDirectory(directory));
    print("File exists: " + FileSystem.exists(filePath));
    print("File contents:");
    print(FileSystem.readText(filePath));

    print("Directory entries:");
    let string[] entries = FileSystem.listDirectory(directory);
    for (string entry in entries) {
        print(entry);
    }

   // FileSystem.deleteFile(filePath);
   // FileSystem.deleteDirectory(directory);
    print("File exists after deletion: " + FileSystem.exists(filePath));
}
