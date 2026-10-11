// Imports the settings module (which re-exposes the type declarations) and
// the type declarations themselves, then uses those types.

import settings_store.{getSetting, describe, lookup}
import settings_types.{SettingsKey, DEFAULT_SETTINGS}

function main() {
    let SettingsKey key = "theme";
    print(getSetting(key));              // system
    print(getSetting("last_backup_at")); // 0
    // The generic lookup takes the key/value types as type arguments.
    print(lookup<SettingsKey, string>(DEFAULT_SETTINGS, "backup_interval_min")); // 0
    print(describe(DEFAULT_SETTINGS));   // system / 0
    print(DEFAULT_SETTINGS.backup_interval_min); // 0
}
