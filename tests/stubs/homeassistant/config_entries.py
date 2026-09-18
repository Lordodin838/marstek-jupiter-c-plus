from typing import Any

class ConfigEntry:
    data: dict = {}
    options: dict = {}
    entry_id = "stub"
    title = "stub"
    runtime_data: Any = None
    def __class_getitem__(cls, item):
        return cls

class ConfigFlowResult(dict):
    pass

class ConfigFlow:
    def __init_subclass__(cls, **kwargs):
        pass

class OptionsFlow:
    pass
