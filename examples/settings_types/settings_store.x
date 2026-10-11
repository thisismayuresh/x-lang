// Imports the declarations from settings_types.x and uses those types.

import settings_types.{SettingsKey, DEFAULT_SETTINGS}

// A generic lookup parameterized by the store's key and value types.
// KeyT/ValueT are inferred from the call site, or given explicitly:
//   lookup<SettingsKey, string>(DEFAULT_SETTINGS, "theme")
export ValueT function<KeyT, ValueT> lookup(object<KeyT, ValueT> store, KeyT key) {
    return store[key];
}

// SettingsKey (a union of literal strings) annotates the lookup key; the
// generic lookup supplies the actual key/value types.
export string function getSetting(SettingsKey key) {
    return lookup<SettingsKey, string>(DEFAULT_SETTINGS, key);
}

// The same DEFAULT_SETTINGS object typed with its key/value parameters.
export string function describe(object<SettingsKey, string> settings) {
    return settings.theme + " / " + settings.backup_interval_min;
}
