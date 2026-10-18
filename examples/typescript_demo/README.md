# TypeScript compile demos

Output of `x compile --target typescript` run against the example programs
in this repository. Regenerate any file with:

```sh
x compile examples/oop_demo.x --target typescript --out examples/typescript_demo/oop_demo.ts
```

| File | Source |
| --- | --- |
| `oop_demo.ts` | `examples/oop_demo.x` — abstract class, inheritance, `super` |
| `match.ts` | `examples/pattern_matching/match.x` — match with guards and patterns |
| `async_demo.ts` | `examples/async_demo.x` — async/await, `Async.all` |
| `exception_hierarchy.ts` | `examples/exceptions/exception_hierarchy.x` — custom exceptions |
| `nested_classes.ts` | `examples/namespaces/nested_classes.x` — namespaces and nested classes |

The emitter translates the entry file **and its imports** into one TypeScript
file. Constructs with no TypeScript equivalent are reported as compile errors
with file/line/column, and nothing is written. See the `x compile` section of
the root README for the full behaviour.
