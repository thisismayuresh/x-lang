# Settings types example

Declare types in one file, import them into another, and use them from a third.
Run the commands from the repository root.

```text
settings_types/
├── settings_types.x   # type declarations + defaults
├── settings_store.x   # imports and uses the types
└── main.x             # imports both and uses the types
```

## TypeScript equivalent

```ts
export type SettingsKey = 'theme' | 'backup_interval_min' | 'last_backup_at';

export const DEFAULT_SETTINGS: Record<SettingsKey, string> = {
  theme: 'system',
  backup_interval_min: '0',
  last_backup_at: '0',
};
```

## How this maps to X

- A union of **string literals** pins the key type to a fixed set of values:
  `type SettingsKey = "theme" | "backup_interval_min" | "last_backup_at";`. A
  string that is not a member is a type error, and so is a plain `string`.
- The generic object form names the key and value types:
  `object<SettingsKey, string>`. X has no separate `Record<...>` spelling.
- X also accepts the TypeScript-style colon annotation for variables and
  fields (`export const DEFAULT_SETTINGS: object<SettingsKey, string> = ...`);
  the type-before-name order shown below is the more usual X style.
- X strings use double quotes — `'c'` is a character literal.

## Files

`settings_types.x` exports the key union and the defaults object:

```x
export type SettingsKey = "theme" | "backup_interval_min" | "last_backup_at";

export const object<SettingsKey, string> DEFAULT_SETTINGS = {
    theme: "system",
    backup_interval_min: "0",
    last_backup_at: "0"
};
```

`settings_store.x` imports the declarations and uses the types in its
signatures. It also exposes a generic lookup parameterized by the store's key
and value types (`<KeyT, ValueT>`):

```x
import settings_types.{SettingsKey, DEFAULT_SETTINGS}

export ValueT function<KeyT, ValueT> lookup(object<KeyT, ValueT> store, KeyT key) {
    return store[key];
}

export string function getSetting(SettingsKey key) {
    return lookup<SettingsKey, string>(DEFAULT_SETTINGS, key);
}

export string function describe(object<SettingsKey, string> settings) {
    return settings.theme + " / " + settings.backup_interval_min;
}
```

`main.x` imports both files and uses the types, passing the type arguments
explicitly to the generic:

```x
import settings_store.{getSetting, describe, lookup}
import settings_types.{SettingsKey, DEFAULT_SETTINGS}

function main() {
    let SettingsKey key = "theme";
    print(getSetting(key));              // system
    print(getSetting("last_backup_at")); // 0
    print(lookup<SettingsKey, string>(DEFAULT_SETTINGS, "backup_interval_min")); // 0
    print(describe(DEFAULT_SETTINGS));   // system / 0
    print(DEFAULT_SETTINGS.backup_interval_min); // 0
}
```

## Notes and limitations

- A file cannot re-export an imported type; a `type`/`export { ... }` name must
  be declared in the file itself. Import the type directly wherever it is used.
- Type aliases are checked by `x check` but are erased at runtime, so an alias
  used inside `object<K, V>` (for example `object<SettingsKey, string>`) is
  resolved by the checker; the runtime accepts any value for that key type.
- String-literal unions are enforced where the checker sees a literal value
  (declaration, assignment, `return`, and call arguments). A value that reaches
  the type through a broad `string` binding is rejected, because the checker
  cannot prove it is a member.
- `export` may prefix a declaration (`export type`, `export const`, `export
  let`, `export function`, `export class`, `export enum`) or be written as a
  bulk list (`export { DEFAULT_SETTINGS };`).

## Run it

```sh
x run examples/settings_types/main.x
x check examples/settings_types/main.x
```
