import System.io.FileSystem

let content = FileSystem.readText("test_data.csv")
print("--- Parsed CSV (First 10 rows) ---")

let lines = content.split("\n")
let header = lines[0].split(",")
print("Columns: " + header.join(" | "))

for (let i = 1; i < 11; i = i + 1) {
    if (i < lines.length) {
        let fields = lines[i].split(",")
        let id = fields[0]
        let name = fields[1]
        let age = fields[2]
        let city = fields[3]
        print("ID: " + id + " | Name: " + name + " | Age: " + age + " | City: " + city)
    }
}