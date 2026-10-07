enum Result {
    SUCCESS,
    FAILURE
}

any function describe(object value) {
    return match value {
        null => "no result",
        [code, ...details] if code == 200 =>
            "success with " + details.length + " detail(s)",
        {kind: "error", message: message} => "error: " + message,
        Result.SUCCESS => "success enum",
        _ => "unrecognized"
    }
}

any function main() {
    print(describe([200, "cached", "fast"]))
    print(describe({kind: "error", message: "offline"}))
    print(describe(Result.SUCCESS))
}
