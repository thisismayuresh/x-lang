// Resume-aware CSV generator: appends `id,value` rows of fresh Aadhaar
// numbers to data.csv, picking up the id from the last line of an existing
// file.  X transpile of the JS original — with static types and
// try-with-resources: the CsvWriter is opened in the try parens and the
// records are written to it inside the block.

import aadhar_generator.getValidAadhar

const string CSV_FILE = "data.csv";

type LastRecord = record { integer id; string? value; };

// A file resource for try-with-resources: constructed with the path (the
// "open") and close()-d by the language when the block exits — on the way
// out, on return, and on throw.  appendText flushes each line immediately,
// so a Ctrl-C stop never loses a written record.
class CsvWriter {
    private string path;
    private boolean closed;

    public CsvWriter(string path) {
        this.path = path;
        this.closed = false;
    }

    public void write(string line) {
        if (this.closed) {
            throw new Exception("write after close: " + this.path);
        }
        FileSystem.appendText(this.path, line);
    }

    public void close() {
        this.closed = true;
    }
}

boolean function ensureFileExists() {
    if (!FileSystem.exists(CSV_FILE)) {
        print(`[START] {CSV_FILE} not found. Creating new file...`);
        FileSystem.writeText(CSV_FILE, "id,value\n");
        print("[START] Starting from index 1");
        return false;
    }
    print(`[START] Found existing file: {CSV_FILE}`);
    return true;
}

LastRecord function getLastRecord() {
    // The JS original stat()s the file and reads only its final 8 KiB
    // through a descriptor; X reads the text directly — fine at example
    // scale.
    let string content = FileSystem.readText(CSV_FILE);
    if (content.isBlank()) {
        return { id: 0, value: null };
    }

    let string[] lines = content.trim().split("\n");
    let string lastLine = lines[lines.length - 1];
    if (lastLine.isEmpty() || lastLine === "id,value") {
        return { id: 0, value: null };
    }

    let string[] parts = lastLine.split(",");
    if (parts.length < 2) {
        return { id: 0, value: null };
    }
    return { id: parseInt(parts[0]), value: parts[1] };
}

let boolean existed = ensureFileExists();
let LastRecord last = getLastRecord();
let integer nextId = last.id + 1;

if (existed && last.id > 0) {
    print(`[RESUME] Last record: {last.id},{last.value}`);
    print(`[RESUME] Continuing from index {nextId}`);
}
else {
    print("[START] No previous records found.");
}

// X has no signal API, so the JS `process.on('SIGINT', ...)` handler has
// no counterpart here — Ctrl-C stops the run, and every record already
// written is on disk.  The writer stays open for the whole loop and is
// close()-d by the language the moment the block exits.
try (let CsvWriter writer = new CsvWriter(CSV_FILE)) {
    while (true) {
        let string value = getValidAadhar();
        writer.write(nextId + "," + value + "\n");
        print(`{nextId},{value}`);

        if (nextId % 10000 === 0) {
            print(`[PROGRESS] Generated {nextId} records`);
        }
        nextId = nextId + 1;
    }
}
