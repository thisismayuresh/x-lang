import System.concurrent.Async

async string function loadLabel(string label, integer delayMilliseconds) {
    await Async.delay(delayMilliseconds);
    return label;
}

async any function main() {
    print("Starting concurrent async work.");

    let string[] labels = await Async.all([
        loadLabel("first", 40),
        loadLabel("second", 10),
        loadLabel("third", 20)
    ]);

    for (string label in labels) {
        print("Completed result: " + label);
    }
}
