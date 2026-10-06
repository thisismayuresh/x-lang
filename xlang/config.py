from __future__ import annotations

import importlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    tomllib = importlib.import_module("tomllib")
except ModuleNotFoundError:
    try:
        tomllib = importlib.import_module("tomli")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "TOML support is unavailable; install the project requirements"
        ) from error


FEATURE_DEFAULTS = {
    "arrow_functions": True,
    "async": True,
    "classes": True,
    "collections": True,
    "concurrency_primitives": True,
    "decorators": True,
    "destructuring": True,
    "enums": True,
    "equality": True,
    "exceptions": True,
    "filesystem": True,
    "generics": True,
    "interfaces": True,
    "loops": True,
    "namespaces": True,
    "object_literals": True,
    "pattern_matching": True,
    "records": True,
    "spread": True,
    "static_methods": True,
    "threads": True,
    "type_checker": True,
    "unions": True,
}


class ConfigError(Exception):
    def __init__(
        self, message: str, path: Path, line: int | None = None, column: int | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.path = path
        self.line = line
        self.column = column


@dataclass
class RunProfile:
    arguments: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)


@dataclass
class XConfig:
    path: Path | None = None
    features: dict[str, bool] = field(
        default_factory=lambda: dict(FEATURE_DEFAULTS)
    )
    run_arguments: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    profiles: dict[str, RunProfile] = field(default_factory=dict)
    default_command: str = "run"
    color: str = "auto"

    def enabled(self, feature: str) -> bool:
        return self.features.get(feature, False)

    def selected_run(self, profile_name: str | None) -> RunProfile:
        if profile_name is None:
            return RunProfile(list(self.run_arguments), dict(self.environment))
        profile = self.profiles.get(profile_name)
        if profile is None:
            raise ConfigError(
                f"Run profile '{profile_name}' is not defined",
                self.path or Path("x.toml"),
            )
        arguments = list(self.run_arguments)
        arguments.extend(profile.arguments)
        environment = dict(self.environment)
        environment.update(profile.environment)
        return RunProfile(arguments, environment)


def discover_config(project_directory: Path) -> Path | None:
    resolved_directory = project_directory.resolve()
    for directory in (resolved_directory, *resolved_directory.parents):
        candidate = directory / "x.toml"
        if candidate.is_file():
            return candidate
    return None


def load_config(
    path: Path | None,
    feature_overrides: list[str] | None = None,
    color_override: str | None = None,
) -> XConfig:
    config_path = None if path is None else path.resolve()
    config = XConfig(path=config_path)
    if config_path is not None:
        try:
            with config_path.open("rb") as config_file:
                data = tomllib.load(config_file)
        except tomllib.TOMLDecodeError as error:
            location_match = re.search(
                r"at line\s+(\d+),\s+column\s+(\d+)", str(error)
            )
            error_line = None
            error_column = None
            if location_match is not None:
                error_line = int(location_match.group(1))
                error_column = int(location_match.group(2))
            raise ConfigError(
                f"Invalid TOML: {error}",
                config_path,
                error_line,
                error_column,
            ) from error
        except OSError as error:
            raise ConfigError(f"Cannot read configuration: {error}", config_path) from error
        _apply_config_tables(config, data, config_path)

    for override in feature_overrides or []:
        _apply_feature_override(config.features, override, config_path or Path("x.toml"))
    if color_override is not None:
        _validate_color(color_override, config_path or Path("x.toml"))
        config.color = color_override
    return config


def load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        contents = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise ConfigError(f"Cannot read environment file: {error}", path) from error

    environment: dict[str, str] = {}
    for line_number, raw_line in enumerate(contents.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()

        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) is None:
            raise ConfigError(
                "Expected an environment assignment in KEY=VALUE form",
                path,
                line_number,
                1,
            )

        value = raw_value.strip()
        if value.startswith(("'", '"')):
            quote = value[0]
            closing_quote = value.find(quote, 1)
            trailing_text = (
                "" if closing_quote < 0 else value[closing_quote + 1:].strip()
            )
            if closing_quote < 0 or (
                trailing_text and not trailing_text.startswith("#")
            ):
                raise ConfigError(
                    "Environment values must use matching quotes with no trailing text",
                    path,
                    line_number,
                    len(key) + 2,
                )
            value = value[1:closing_quote]
        else:
            comment_start = re.search(r"\s+#", value)
            if comment_start is not None:
                value = value[:comment_start.start()].rstrip()
        environment[key] = value
    return environment


def _apply_config_tables(
    config: XConfig, data: dict[str, Any], config_path: Path
) -> None:
    _validate_keys(data, {"features", "run", "cli"}, "root", config_path)

    feature_values = data.get("features", {})
    if not isinstance(feature_values, dict):
        raise ConfigError("[features] must be a TOML table", config_path)
    for feature_name, enabled in feature_values.items():
        if feature_name not in FEATURE_DEFAULTS:
            known_features = ", ".join(sorted(FEATURE_DEFAULTS))
            raise ConfigError(
                f"Unknown feature '{feature_name}'. Available features: {known_features}",
                config_path,
            )
        if not isinstance(enabled, bool):
            raise ConfigError(
                f"Feature '{feature_name}' must be true or false", config_path
            )
        config.features[feature_name] = enabled

    cli_values = data.get("cli", {})
    if not isinstance(cli_values, dict):
        raise ConfigError("[cli] must be a TOML table", config_path)
    _validate_keys(cli_values, {"default-command", "color"}, "[cli]", config_path)
    default_command = cli_values.get("default-command", "run")
    if default_command not in {"run", "check", "build"}:
        raise ConfigError(
            "[cli].default-command must be 'run', 'check', or 'build'", config_path
        )
    config.default_command = default_command
    color = cli_values.get("color", "auto")
    if not isinstance(color, str):
        raise ConfigError("[cli].color must be a string", config_path)
    _validate_color(color, config_path)
    config.color = color

    run_values = data.get("run", {})
    if not isinstance(run_values, dict):
        raise ConfigError("[run] must be a TOML table", config_path)
    _validate_keys(
        run_values, {"args", "environment", "profiles"}, "[run]", config_path
    )
    config.run_arguments = _string_list(run_values.get("args", []), "[run].args", config_path)
    config.environment = _string_table(
        run_values.get("environment", {}), "[run].environment", config_path
    )
    profiles = run_values.get("profiles", {})
    if not isinstance(profiles, dict):
        raise ConfigError("[run.profiles] must be a TOML table", config_path)
    for profile_name, profile_values in profiles.items():
        if not isinstance(profile_values, dict):
            raise ConfigError(
                f"Profile '{profile_name}' must be a TOML table", config_path
            )
        _validate_keys(
            profile_values,
            {"args", "environment"},
            f"[run.profiles.{profile_name}]",
            config_path,
        )
        config.profiles[profile_name] = RunProfile(
            _string_list(
                profile_values.get("args", []),
                f"[run.profiles.{profile_name}].args",
                config_path,
            ),
            _string_table(
                profile_values.get("environment", {}),
                f"[run.profiles.{profile_name}].environment",
                config_path,
            ),
        )


def _apply_feature_override(
    features: dict[str, bool], override: str, config_path: Path
) -> None:
    if "=" not in override:
        raise ConfigError(
            "--feature expects NAME=on or NAME=off", config_path
        )
    feature_name, raw_value = override.split("=", 1)
    feature_name = feature_name.replace("-", "_")
    normalized_value = raw_value.lower()
    if feature_name not in FEATURE_DEFAULTS:
        raise ConfigError(f"Unknown feature '{feature_name}'", config_path)
    if normalized_value not in {"on", "off", "true", "false"}:
        raise ConfigError(
            f"Feature override '{feature_name}' must be on/off or true/false",
            config_path,
        )
    features[feature_name] = normalized_value in {"on", "true"}


def _validate_keys(
    values: dict[str, Any],
    allowed: set[str],
    section_name: str,
    config_path: Path,
) -> None:
    unknown_keys = sorted(set(values) - allowed)
    if unknown_keys:
        keys = ", ".join(unknown_keys)
        raise ConfigError(f"Unknown key(s) in {section_name}: {keys}", config_path)


def _string_list(value: Any, setting_name: str, config_path: Path) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigError(f"{setting_name} must be an array of strings", config_path)
    return list(value)


def _string_table(
    value: Any, setting_name: str, config_path: Path
) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ConfigError(f"{setting_name} must be a TOML table", config_path)
    invalid_keys = [
        name for name, content in value.items()
        if not isinstance(name, str) or not isinstance(content, str)
    ]
    if invalid_keys:
        raise ConfigError(f"{setting_name} must contain only string values", config_path)
    return dict(value)


def _validate_color(color: str, config_path: Path) -> None:
    if color not in {"auto", "always", "never"}:
        raise ConfigError(
            "Color mode must be 'auto', 'always', or 'never'", config_path
        )
