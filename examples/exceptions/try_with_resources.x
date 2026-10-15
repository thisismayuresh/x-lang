// Try-with-resources: `try (let name = resource) { ... }` binds a resource
// and calls its close() automatically when the block exits — on the way out,
// on return, and on throw. Multiple bindings close last-in-first-out.

class Connection {
    private string id;

    public Connection(string id) {
        this.id = id;
        print("open   " + this.id);
    }

    public string getId() { return this.id; }

    public void close() {
        print("close  " + this.id);
    }
}

any function main() {
    // Normal exit — close() runs after the block.
    try (let Connection db = new Connection("db")) {
        print("using " + db.getId());
    }
    print("---");

    // The body throws — close() still runs before the catch.
    try (let Connection db = new Connection("failing-db")) {
        throw new Exception("query failed");
    }
    catch (Exception error) {
        print("caught: " + error.message);
    }
    print("---");

    // Multiple resources — closed in reverse order (LIFO).
    try (let Connection primary = new Connection("primary"),
         let Connection replica = new Connection("replica")) {
        print("using " + primary.getId() + " + " + replica.getId());
    }
}
