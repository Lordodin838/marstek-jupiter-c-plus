class DataUpdateCoordinator:
    def __init__(self, hass, logger, config_entry=None, name=None,
                 update_interval=None, always_update=True):
        self.hass = hass
        self.logger = logger
        self.config_entry = config_entry
        self.name = name
        self.update_interval = update_interval
        self.data = None
        self.last_update_success = True
    def __class_getitem__(cls, item):
        return cls


class CoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator
    def __class_getitem__(cls, item):
        return cls
