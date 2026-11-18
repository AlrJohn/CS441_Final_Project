"""Load JSON scenarios and reject inconsistent inputs before running algorithms."""

import json
from math import isfinite
from pathlib import Path

from .models import AccessPoint, PowerSetting, Scenario, User


def _require_keys(record, expected, context):
    """Check an exact JSON object schema and give a useful field-level error."""
    if not isinstance(record, dict):
        raise ValueError(f"{context} must be a JSON object.")
    missing = set(expected) - set(record)
    extra = set(record) - set(expected)
    if missing or extra:
        raise ValueError(f"{context}: missing fields {sorted(missing)}; unexpected fields {sorted(extra)}.")


def _check_number(value, name, minimum=None, positive=False):
    """Reject booleans, NaN/infinity, and values outside a field's allowed range."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number.")
    if positive and value <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")


def _check_id(value, name):
    """Require a nonempty string ID/name; preserve its exact spelling."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string.")


def scenario_from_dict(data: dict) -> Scenario:
    """Convert parsed JSON into validated shared objects, including coverage sets.

    Used by both file loading and in-memory Streamlit uploads. No temporary
    files or alternate unit models are needed. Unknown legacy fields are rejected.
    """
    _require_keys(data, ("scenario_id", "description", "interval_hours", "users", "access_points"), "scenario")
    if not isinstance(data["users"], list) or not isinstance(data["access_points"], list):
        raise ValueError("users and access_points must be JSON lists.")
    users = []
    for record in data["users"]:
        _require_keys(record, ("user_id", "x", "y", "critical", "demand_mbps"), "device")
        users.append(User(**record))

    access_points = []
    for record in data["access_points"]:
        _require_keys(record, ("ap_id", "x", "y", "highest_setting", "settings"), "AP")
        if not isinstance(record["settings"], dict):
            raise ValueError("AP settings must be an object of named settings.")
        settings = {}
        for name, setting in record["settings"].items():
            _require_keys(setting, ("electrical_watts", "capacity_mbps", "covered_user_ids"), f"setting {name}")
            coverage = setting["covered_user_ids"]
            if not isinstance(coverage, list) or not all(isinstance(item, str) for item in coverage):
                raise ValueError(f"Setting {name}: covered_user_ids must be a list of string IDs.")
            settings[name] = PowerSetting(setting["electrical_watts"], setting["capacity_mbps"], set(coverage))
        access_points.append(AccessPoint(
            record["ap_id"], record["x"], record["y"], record["highest_setting"], settings
        ))
    scenario = Scenario(
        data["scenario_id"], data["description"], data["interval_hours"], users, access_points
    )
    validate_scenario(scenario)
    return scenario


def load_scenario(path: str | Path) -> Scenario:
    """Read a UTF-8 JSON scenario; errors include its filename for troubleshooting."""
    path = Path(path)
    try:
        with path.open(encoding="utf-8-sig") as scenario_file:
            data = json.load(scenario_file)
        return scenario_from_dict(data)
    except (ValueError, TypeError) as error:
        raise ValueError(f"{path.name}: {error}") from error


def validate_scenario(scenario: Scenario) -> None:
    """Validate values and references; legitimate but infeasible cases are allowed.

    Demand/capacity are Mbps, electrical draw is W, interval is hours, and x/y
    share local plotting units. No relationship between watts and capacity or
    coverage is silently assumed. Maximum electrical draw identifies highest.
    """
    _check_id(scenario.scenario_id, "scenario_id")
    if not isinstance(scenario.description, str):
        raise ValueError("description must be a string.")
    _check_number(scenario.interval_hours, "interval_hours", positive=True)
    user_ids = set()
    for user in scenario.users:
        _check_id(user.user_id, "user_id")
        if user.user_id in user_ids:
            raise ValueError(f"Duplicate device ID: {user.user_id}")
        user_ids.add(user.user_id)
        if type(user.critical) is not bool:
            raise ValueError(f"Device {user.user_id}: critical must be true or false.")
        _check_number(user.x, f"{user.user_id}.x")
        _check_number(user.y, f"{user.user_id}.y")
        _check_number(user.demand_mbps, f"{user.user_id}.demand_mbps", positive=True)

    ap_ids = set()
    for access_point in scenario.access_points:
        _check_id(access_point.ap_id, "ap_id")
        if access_point.ap_id in ap_ids:
            raise ValueError(f"Duplicate AP ID: {access_point.ap_id}")
        ap_ids.add(access_point.ap_id)
        _check_number(access_point.x, f"{access_point.ap_id}.x")
        _check_number(access_point.y, f"{access_point.ap_id}.y")
        if not access_point.settings:
            raise ValueError(f"AP {access_point.ap_id} must have at least one ON setting.")
        _check_id(access_point.highest_setting, "highest_setting")
        if access_point.highest_setting not in access_point.settings:
            raise ValueError(f"AP {access_point.ap_id} has an unknown highest_setting.")
        maximum_watts = 0.0
        for name, setting in access_point.settings.items():
            _check_id(name, "setting name")
            if name.lower() == "off":
                raise ValueError("An off setting is outside this all-on model.")
            _check_number(setting.electrical_watts, f"{access_point.ap_id}.{name}.watts", positive=True)
            _check_number(setting.capacity_mbps, f"{access_point.ap_id}.{name}.capacity_mbps", minimum=0)
            if not isinstance(setting.covered_user_ids, set):
                raise ValueError("Model coverage must be a set of known string device IDs.")
            if not setting.covered_user_ids <= user_ids:
                raise ValueError(f"AP {access_point.ap_id}.{name} covers unknown device IDs.")
            maximum_watts = max(maximum_watts, setting.electrical_watts)
        highest = access_point.settings[access_point.highest_setting]
        if highest.electrical_watts != maximum_watts:
            raise ValueError(f"AP {access_point.ap_id}: highest_setting must have maximal electrical draw.")
