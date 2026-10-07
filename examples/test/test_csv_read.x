import System.io.FileSystem

let content = FileSystem.readText("test_data.csv")
print("File content:")
print(content)

print("\n--- First 10 rows ---")
let lines = content.split("\n")
let header = lines[0]
print("Header: " + header)

for (let i = 1; i < 11; i = i + 1) {
    if (i < lines.length) {
        print("Row " + i + ": " + lines[i])
    }
}