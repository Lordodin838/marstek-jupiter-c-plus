from enum import StrEnum

class EntityCategory(StrEnum):
    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"

class Platform(StrEnum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"

class UnitOfPower(StrEnum):
    WATT = "W"

class UnitOfEnergy(StrEnum):
    KILO_WATT_HOUR = "kWh"

class UnitOfElectricPotential(StrEnum):
    VOLT = "V"

class UnitOfElectricCurrent(StrEnum):
    AMPERE = "A"

class UnitOfTemperature(StrEnum):
    CELSIUS = "°C"

PERCENTAGE = "%"
CONF_HOST = "host"
CONF_PORT = "port"
