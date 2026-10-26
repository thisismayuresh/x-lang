# Aadhaar CSV generator

The JavaScript program from the question, transpiled to statically-typed X:

- **`aadhar_generator.x`** — `getValidAadhar()` builds twelve random digits
  and rejects them until the Verhoeff checksum validates (plus the trivial
  all-same-digit rejection). Exports only the generator; the tables and
  `isValidAadhar` stay module-private.
- **`main.x`** — resumes from the last `id,value` row of `data.csv`
  (creating it with a header when missing) and appends forever:

  ```x
  try (let CsvWriter writer = new CsvWriter(CSV_FILE)) {
      while (true) {
          let string value = getValidAadhar();
          writer.write(nextId + "," + value + "\n");
          ...
      }
  }
  catch (Exception error) {
      print(`[STOP] {error.message}`);
  }
  ```

  The `CsvWriter` is *opened* by the try parens and `close()`-d by the
  language on normal exit, on return, and on throw — always before the
  matching `catch` runs. The catch is optional (resource-only `try` acts
  like `try/finally`), but it turns a failed append into a `[STOP]` line
  instead of a crash. `appendText` flushes every record immediately, so a
  Ctrl-C stop never loses a written row.

Both files pass `x check` with `--feature strict_typing=on`. The JS
`process.on('SIGINT', ...)` handler has no X counterpart — Ctrl-C ends the
run; the id resumes on the next one.

## Run

```sh
x run examples/aadhar/main.x
```

The CSV is created in the current working directory; run it a second time
and it prints `[RESUME] Continuing from index N`. It runs until
interrupted — stop it with Ctrl-C (or `timeout 5 x run ...`).
