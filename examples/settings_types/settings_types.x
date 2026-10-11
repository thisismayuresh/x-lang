// Shared settings declarations, imported by settings_store.x and main.x.
//
// The original TypeScript shape is:
//
//   export type SettingsKey = 'theme' | 'backup_interval_min' | 'last_backup_at';
//   export const DEFAULT_SETTINGS: Record<SettingsKey, string> = { ... };
//
// X spells string literals with double quotes and writes the object form as
// `object<Key, Value>` with the type before the name.

export type SettingsKey = "theme" | "backup_interval_min" | "last_backup_at";

export const object<SettingsKey, string> DEFAULT_SETTINGS = {
    theme: "system",
    backup_interval_min: "0",
    last_backup_at: "0"
};
