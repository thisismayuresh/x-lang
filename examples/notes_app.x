import System.io.Console
import System.io.FileSystem
import System.utils.Collections.HashMap

// Notes Application - Terminal-based note manager with file-based storage
// Features: Add, List, View, Delete, Search notes with switch-case menu

let string NOTES_FILE = "notes_db.json"

    let running = true
    while (running) {
        showMenu()
        let choice = Console.input("Enter your choice: ")
        
        switch (choice) {
            case "1": {
                addNote()
            }
            case "2": {
                listNotes()
            }
            case "3": {
                viewNote()
            }
            case "4": {
                deleteNote()
            }
            case "5": {
                searchNotes()
            }
            case "6": {
                Console.print("Goodbye!")
                running = false
            }
            default: {
                Console.print("Invalid choice. Please try again.")
            }
        }
        Console.print("")
    }

function showMenu() {
    Console.print("┌──────────────────────────────────────┐")
    Console.print("│           MAIN MENU                  │")
    Console.print("├──────────────────────────────────────┤")
    Console.print("│  1. Add Note                         │")
    Console.print("│  2. List All Notes                   │")
    Console.print("│  3. View Note by ID                  │")
    Console.print("│  4. Delete Note                      │")
    Console.print("│  5. Search Notes                     │")
    Console.print("│  6. Exit                             │")
    Console.print("└──────────────────────────────────────┘")
}

function addNote() {
    Console.print("\n--- Add New Note ---")
    let title = Console.input("Title: ")
    if (title == "") {
        Console.print("Error: Title cannot be empty!")
        return
    }
    
    Console.print("Content (press Enter twice to finish):")
    let content = ""
    let line = ""
    let emptyCount = 0
    while (true) {
        line = Console.input("")
        if (line == "") {
            emptyCount = emptyCount + 1
            if (emptyCount >= 2) {
                break
            }
        } else {
            emptyCount = 0
            if (content != "") {
                content = content + "\n"
            }
            content = content + line
        }
    }
    
    if (content == "") {
        Console.print("Error: Content cannot be empty!")
        return
    }
    
    let tagsInput = Console.input("Tags (comma-separated, optional): ")
    let tags = []
    if (tagsInput != "") {
        tags = tagsInput.split(",")
        for (let i = 0; i < tags.length; i = i + 1) {
            tags[i] = tags[i].trim()
        }
    }
    
    let notes = loadNotes()
    let id = generateId()
    let note = {
        "id": id,
        "title": title,
        "content": content,
        "tags": tags,
        "created": now(),
        "updated": now()
    }
    notes.set(id, note)
    saveNotes(notes)
    Console.print("Note added successfully! ID: " + id)
}

function listNotes() {
    let notes = loadNotes()
    let keys = notes.keys()
    
    Console.print("\n--- All Notes ---")
    if (keys.length == 0) {
        Console.print("No notes found.")
        return
    }
    
    Console.print(String.format("%-10s %-30s %-20s %s", "ID", "TITLE", "TAGS", "CREATED"))
    Console.print(String.repeat("-", 80))
    
    for (let key of keys) {
        let note = notes.get(key)
        let tagsStr = note.tags.join(", ")
        if (tagsStr.length > 18) {
            tagsStr = tagsStr.substring(0, 15) + "..."
        }
        let dateStr = formatDate(note.created)
        let title = note.title
        if (title.length > 28) {
            title = title.substring(0, 25) + "..."
        }
        Console.print(String.format("%-10s %-30s %-20s %s", note.id, title, tagsStr, dateStr))
    }
}

function viewNote() {
    let id = Console.input("Enter note ID: ")
    let notes = loadNotes()
    
    if (!notes.has(id)) {
        Console.print("Note not found!")
        return
    }
    
    let note = notes.get(id)
    Console.print("\n--- Note Details ---")
    Console.print("ID: " + note.id)
    Console.print("Title: " + note.title)
    Console.print("Tags: " + note.tags.join(", "))
    Console.print("Created: " + formatDate(note.created))
    Console.print("Updated: " + formatDate(note.updated))
    Console.print("\nContent:")
    Console.print(note.content)
}

function deleteNote() {
    let id = Console.input("Enter note ID to delete: ")
    let notes = loadNotes()
    
    if (!notes.has(id)) {
        Console.print("Note not found!")
        return
    }
    
    let confirm = Console.input("Are you sure? (y/N): ")
    if (confirm.toLowerCase() != "y") {
        Console.print("Deletion cancelled.")
        return
    }
    
    notes.remove(id)
    saveNotes(notes)
    Console.print("Note deleted successfully!")
}

function searchNotes() {
    let query = Console.input("Search query: ")
    if (query == "") {
        Console.print("Search query cannot be empty!")
        return
    }
    
    let notes = loadNotes()
    let keys = notes.keys()
    let found = false
    let lowerQuery = query.toLowerCase()
    
    Console.print("\n--- Search Results ---")
    for (let key of keys) {
        let note = notes.get(key)
        let foundMatch = false
        if (note.title.toLowerCase().indexOf(lowerQuery) >= 0) foundMatch = true
        if (note.content.toLowerCase().indexOf(lowerQuery) >= 0) foundMatch = true
        for (let tag of note.tags) {
            if (tag.toLowerCase().indexOf(lowerQuery) >= 0) {
                foundMatch = true
                break
            }
        }
        
        if (foundMatch) {
            if (!found) {
                Console.print(String.format("%-10s %-30s %-20s %s", "ID", "TITLE", "TAGS", "CREATED"))
                Console.print(String.repeat("-", 80))
                found = true
            }
            let tagsStr = note.tags.join(", ")
            if (tagsStr.length > 18) tagsStr = tagsStr.substring(0, 15) + "..."
            let title = note.title
            if (title.length > 28) title = title.substring(0, 25) + "..."
            Console.print(String.format("%-10s %-30s %-20s %s", note.id, title, tagsStr, formatDate(note.created)))
        }
    }
    
    if (!found) {
        Console.print("No matching notes found.")
    }
}

function loadNotes() {
    let content = FileSystem.readText(NOTES_FILE)
    if (content == "") return HashMap.create()
    return parseNotes(content)
}

function saveNotes(notes) {
    let json = serializeNotes(notes)
    FileSystem.writeText(NOTES_FILE, json)
}

function parseNotes(json) {
    let notes = HashMap.create()
    if (json == "{}" || json.length < 3) return notes
    
    let inner = json.substring(1, json.length - 1)
    let entries = splitTopLevel(inner)
    
    for (let entry of entries) {
        if (entry.trim() == "") continue
        let colonIdx = entry.indexOf(":")
        if (colonIdx < 0) continue
        let key = entry.substring(0, colonIdx).trim().replace("\"", "")
        let value = entry.substring(colonIdx + 1).trim()
        if (value.startsWith("{") && value.endsWith("}")) {
            notes.set(key, parseNote(value))
        }
    }
    return notes
}

function parseNote(json) {
    let note = {}
    let inner = json.substring(1, json.length - 1)
    let fields = splitTopLevel(inner)
    
    for (let field of fields) {
        let colonIdx = field.indexOf(":")
        if (colonIdx < 0) continue
        let key = field.substring(0, colonIdx).trim().replace("\"", "")
        let value = field.substring(colonIdx + 1).trim()
        
        if (key == "tags") {
            if (value.startsWith("[") && value.endsWith("]")) {
                let tagsInner = value.substring(1, value.length - 1)
                if (tagsInner.trim() != "") {
                    let tags = tagsInner.split(",")
                    for (let i = 0; i < tags.length; i = i + 1) {
                        tags[i] = tags[i].trim().replace("\"", "")
                    }
                    note[key] = tags
                } else {
                    note[key] = []
                }
            }
        } else if (value.startsWith("\"") && value.endsWith("\"")) {
            note[key] = value.substring(1, value.length - 1)
        } else if (value == "true" || value == "false") {
            note[key] = value == "true"
        } else {
            note[key] = value
        }
    }
    return note
}

function splitTopLevel(str) {
    let parts = []
    let current = ""
    let depth = 0
    let inString = false
    let escape = false
    
    for (let i = 0; i < str.length; i = i + 1) {
        let char = str[i]
        
        if (escape) {
            escape = false
            current = current + char
            continue
        }
        
        if (char == "\\") {
            escape = true
            current = current + char
            continue
        }
        
        if (char == "\"" && !escape) {
            inString = !inString
        }
        
        if (!inString) {
            if (char == "{" || char == "[" ) {
                depth = depth + 1
            } else if (char == "}" || char == "]") {
                depth = depth - 1
            } else if (char == "," && depth == 0) {
                parts.push(current.trim())
                current = ""
                continue
            }
        }
        current = current + char
    }
    
    if (current.trim() != "") {
        parts.push(current.trim())
    }
    return parts
}

function serializeNotes(notes) {
    let parts = []
    let keys = notes.keys()
    
    for (let key of keys) {
        let note = notes.get(key)
        parts.push("\"" + key + "\":" + serializeNote(note))
    }
    return "{" + parts.join(",") + "}"
}

function serializeNote(note) {
    let parts = []
    let keys = ["id", "title", "content", "tags", "created", "updated"]
    
    for (let key of keys) {
        let value = note[key]
        if (key == "tags") {
            let tagParts = []
            for (let tag of value) {
                tagParts.push("\"" + tag + "\"")
            }
            parts.push("\"" + key + "\":[" + tagParts.join(",") + "]")
        } else if (typeOf(value) == "string") {
            parts.push("\"" + key + "\":\"" + escapeJson(value) + "\"")
        } else if (typeOf(value) == "boolean") {
            parts.push("\"" + key + "\":" + (value ? "true" : "false"))
        } else {
            parts.push("\"" + key + "\":" + value)
        }
    }
    return "{" + parts.join(",") + "}"
}

function escapeJson(str) {
    return str.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
}

function generateId() {
    return now().toString(36) + Math.random().toString(36).substring(2, 9)
}

function formatDate(timestamp) {
    return timestamp.toString()
}

function now() {
    return Math.floor(Math.random() * 1000000000000)
}

function main() {
    if (!FileSystem.exists(NOTES_FILE)) {
        FileSystem.writeText(NOTES_FILE, "{}")
    }

    Console.print("╔══════════════════════════════════════╗")
    Console.print("║       X NOTES APPLICATION v1.0       ║")
    Console.print("╚══════════════════════════════════════╝")
    Console.print("")

    let running = true
    while (running) {
        showMenu()
        let choice = Console.input("Enter your choice: ")
        
        switch (choice) {
            case "1": {
                addNote()
            }
            case "2": {
                listNotes()
            }
            case "3": {
                viewNote()
            }
            case "4": {
                deleteNote()
            }
            case "5": {
                searchNotes()
            }
            case "6": {
                Console.print("Goodbye!")
                running = false
            }
            default: {
                Console.print("Invalid choice. Please try again.")
            }
        }
        Console.print("")
    }
}


main()