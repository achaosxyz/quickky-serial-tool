"""Pure configuration defaults and normalization."""

SERIAL_PARITIES = {"None", "Even", "Odd", "Mark", "Space"}
FLOW_CONTROLS = {"None", "Hardware", "Software"}
MODES = {"TEXT", "HEX"}
ENCODINGS = {"UTF-8", "ASCII"}
LINE_ENDINGS = {"CR", "LF", "CRLF"}
THEMES = {"light", "dark"}
LANGUAGES = {"system", "zh_CN", "en_US"}

def get_default_config():
    return {
        "last_port_main": "",
        "last_port_secondary": "",
        "last_log_directory": "",
        "port_configs": {},
        "quick_command_groups": [],
        "send_history": [],
        "command_panel_visible": True,
        "dual_panel_mode": False,
        "theme": "light",
        "language": "system",
        "global_settings": {
            "receive_buffer_size": 10000,
            "send_history_max": 200,
            "fontSize": 9,
            "reconnect_interval": 5,
        },
    }

def get_default_port_config():
    return {
        "serial_settings": {
            "baudrate": 115200,
            "parity": "None",
            "bytesize": 8,
            "stopbits": 1,
            "flow_control": "None",
        },
        "receive_settings": {
            "mode": "TEXT",
            "encoding": "UTF-8",
            "log_mode": False,
            "save_log": False,
            "auto_reconnect": False,
            "auto_scroll": True,
        },
        "send_settings": {
            "mode": "TEXT",
            "line_ending": "CRLF",
            "loop_send": False,
            "loop_period_ms": 1000,
        },
        "send_text": "",
    }

def _valid_int(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum

def _valid_number(value, allowed):
    return type(value) in (int, float) and value in allowed

def _valid_bool(value):
    return type(value) is bool

def normalize_port_config(raw):
    defaults = get_default_port_config()
    if not isinstance(raw, dict):
        return defaults

    serial_raw = raw.get("serial_settings", {})
    if not isinstance(serial_raw, dict):
        serial_raw = {}
    serial = defaults["serial_settings"]
    if _valid_int(serial_raw.get("baudrate"), 1, 4_000_000):
        serial["baudrate"] = serial_raw["baudrate"]
    if isinstance(serial_raw.get("parity"), str) and serial_raw.get("parity") in SERIAL_PARITIES:
        serial["parity"] = serial_raw["parity"]
    if type(serial_raw.get("bytesize")) is int and serial_raw["bytesize"] in {5, 6, 7, 8}:
        serial["bytesize"] = serial_raw["bytesize"]
    if _valid_number(serial_raw.get("stopbits"), {1, 1.5, 2}):
        serial["stopbits"] = serial_raw["stopbits"]
    if isinstance(serial_raw.get("flow_control"), str) and serial_raw.get("flow_control") in FLOW_CONTROLS:
        serial["flow_control"] = serial_raw["flow_control"]

    receive_raw = raw.get("receive_settings", {})
    if not isinstance(receive_raw, dict):
        receive_raw = {}
    receive = defaults["receive_settings"]
    if isinstance(receive_raw.get("mode"), str) and receive_raw.get("mode") in MODES:
        receive["mode"] = receive_raw["mode"]
    if isinstance(receive_raw.get("encoding"), str) and receive_raw.get("encoding") in ENCODINGS:
        receive["encoding"] = receive_raw["encoding"]
    for key in ("log_mode", "auto_reconnect", "auto_scroll"):
        if _valid_bool(receive_raw.get(key)):
            receive[key] = receive_raw[key]
    # Log file selection is session-only.
    receive["save_log"] = False

    send_raw = raw.get("send_settings", {})
    if not isinstance(send_raw, dict):
        send_raw = {}
    send = defaults["send_settings"]
    if isinstance(send_raw.get("mode"), str) and send_raw.get("mode") in MODES:
        send["mode"] = send_raw["mode"]
    if isinstance(send_raw.get("line_ending"), str) and send_raw.get("line_ending") in LINE_ENDINGS:
        send["line_ending"] = send_raw["line_ending"]
    if _valid_bool(send_raw.get("loop_send")):
        send["loop_send"] = send_raw["loop_send"]
    if _valid_int(send_raw.get("loop_period_ms"), 1, 3_600_000):
        send["loop_period_ms"] = send_raw["loop_period_ms"]

    if isinstance(raw.get("send_text"), str):
        defaults["send_text"] = raw["send_text"]
    return defaults

def normalize_quick_command_groups(raw):
    if not isinstance(raw, list):
        return []
    groups = []
    for group in raw:
        if not isinstance(group, dict) or not isinstance(group.get("name"), str):
            continue
        commands_raw = group.get("commands", [])
        if not isinstance(commands_raw, list):
            commands_raw = []
        commands = []
        for command in commands_raw:
            if not isinstance(command, dict):
                continue
            data = command.get("data", command.get("command"))
            if not isinstance(data, str):
                continue
            mode = command.get("mode", "TEXT")
            commands.append({
                "name": command.get("name", "") if isinstance(command.get("name", ""), str) else "",
                "data": data,
                "command": data,
                "mode": mode if isinstance(mode, str) and mode in MODES else "TEXT",
            })
        groups.append({"name": group["name"], "commands": commands})
    return groups

def normalize_send_history(raw):
    if not isinstance(raw, list):
        return []
    history = []
    for item in raw:
        if isinstance(item, str):
            history.append({"data": item, "mode": "TEXT", "time": ""})
            continue
        if not isinstance(item, dict) or not isinstance(item.get("data"), str):
            continue
        mode = item.get("mode", "TEXT")
        time_text = item.get("time", "")
        history.append({
            "data": item["data"],
            "mode": mode if isinstance(mode, str) and mode in MODES else "TEXT",
            "time": time_text if isinstance(time_text, str) else "",
        })
    return history

def normalize_config(raw):
    """Normalize external JSON and discard unknown fields."""
    if not isinstance(raw, dict):
        raise ValueError("配置根节点必须是 JSON 对象")
    config = get_default_config()
    for key in ("last_port_main", "last_port_secondary", "last_log_directory"):
        if isinstance(raw.get(key), str):
            config[key] = raw[key]
    for key in ("command_panel_visible", "dual_panel_mode"):
        if _valid_bool(raw.get(key)):
            config[key] = raw[key]
    if isinstance(raw.get("theme"), str) and raw.get("theme") in THEMES:
        config["theme"] = raw["theme"]
    if isinstance(raw.get("language"), str) and raw["language"] in LANGUAGES:
        config["language"] = raw["language"]

    settings_raw = raw.get("global_settings", {})
    if isinstance(settings_raw, dict):
        settings = config["global_settings"]
        if _valid_int(settings_raw.get("receive_buffer_size"), 1000, 100000):
            settings["receive_buffer_size"] = settings_raw["receive_buffer_size"]
        if _valid_int(settings_raw.get("send_history_max"), 50, 1000):
            settings["send_history_max"] = settings_raw["send_history_max"]
        if _valid_int(settings_raw.get("fontSize"), 6, 20):
            settings["fontSize"] = settings_raw["fontSize"]
        if _valid_int(settings_raw.get("reconnect_interval"), 1, 30):
            settings["reconnect_interval"] = settings_raw["reconnect_interval"]

    port_configs = raw.get("port_configs", {})
    if isinstance(port_configs, dict):
        config["port_configs"] = {
            port: normalize_port_config(value)
            for port, value in port_configs.items()
            if isinstance(port, str) and port
        }
    config["quick_command_groups"] = normalize_quick_command_groups(raw.get("quick_command_groups", []))
    history = normalize_send_history(raw.get("send_history", []))
    config["send_history"] = history[:config["global_settings"]["send_history_max"]]
    return config
