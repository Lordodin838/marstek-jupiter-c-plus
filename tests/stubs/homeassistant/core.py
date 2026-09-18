from enum import Enum

class HomeAssistant:
    pass

class ServiceCall:
    pass

ServiceResponse = dict

class SupportsResponse(Enum):
    ONLY = "only"
    OPTIONAL = "optional"

def callback(func):
    return func
