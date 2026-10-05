# Import and export examples

These small projects show how an exported function can be imported from another
X source file. Run the commands from the repository root.

## Simple: sibling files

```text
simple/
├── greeting.x
└── main.x
```

`main.x` imports `greeting.x` because they are in the same folder:

```x
import greeting.sayGreet
import greeting.sayHello
```

The first part, `greeting`, selects `greeting.x`; the final part names the
exported declaration. Both functions are exported from that file.

To import every export directly, use `*`. Add an alias to group the exports
under one name:

```x
import greeting.*
import greeting.* as Greet
```

The example uses the aliased form and calls the functions as
`Greet.sayGreet()` and `Greet.sayHello()`.

Run it with:

```sh
x run examples/import_export/simple/main.x
```

## Folder levels: project-root path

```text
folder_levels/
├── app/
│   └── main.x
└── lib/
    └── messages/
        └── greeting.x
```

The app imports the exported function with the dotted folder path followed by
the function name:

```x
import examples.import_export.folder_levels.lib.messages.greeting
```

Here `examples.import_export.folder_levels.lib.messages` selects the folders
and `greeting` selects the exported declaration from `greeting.x`.

Run it from the repository root with:

```sh
x run examples/import_export/folder_levels/app/main.x
```
