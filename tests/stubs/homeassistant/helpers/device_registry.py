CONNECTION_NETWORK_MAC = "mac"

class DeviceInfo(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
