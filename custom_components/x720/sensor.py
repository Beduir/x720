import importlib
import struct
import logging

from time import time, sleep

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    CONF_NAME, CONF_MONITORED_CONDITIONS)
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

CONF_I2C_ADDRESS = 'i2c_address'
CONF_I2C_BUS = 'i2c_bus'

DEFAULT_NAME = 'X720 Sensor'
DEFAULT_I2C_ADDRESS = 0x36
DEFAULT_I2C_BUS = 1

SENSOR_VOLTAGE = 'voltage'
SENSOR_CAPACITY = 'capacity'
SENSOR_TYPES = {
    SENSOR_VOLTAGE: ['Voltage', 'V'],
    SENSOR_CAPACITY: ['Capacity', '%']
}

DEFAULT_MONITORED = [SENSOR_VOLTAGE, SENSOR_CAPACITY]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_I2C_ADDRESS, default=DEFAULT_I2C_ADDRESS):
        cv.positive_int,
    vol.Optional(CONF_MONITORED_CONDITIONS, default=DEFAULT_MONITORED):
        vol.All(cv.ensure_list, [vol.In(SENSOR_TYPES)]),
    vol.Optional(CONF_I2C_BUS, default=DEFAULT_I2C_BUS): cv.positive_int,
})

async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the X720 sensor."""
    name = config.get(CONF_NAME)

    sensor_handler = await hass.async_add_job(_setup_x720, config)
    if sensor_handler is None:
        return

    dev = []
    for variable in config[CONF_MONITORED_CONDITIONS]:
        dev.append(X720Sensor(
            sensor_handler, variable, SENSOR_TYPES[variable][1], name))

    async_add_entities(dev)
    return

def _setup_x720(config):
    """Set up and configure the X720 sensor."""
    from smbus import SMBus

    sensor_handler = None
    try:
        i2c_address = config.get(CONF_I2C_ADDRESS)
        bus = SMBus(config.get(CONF_I2C_BUS))
        sensor = X720(i2c_address, bus)

    except (RuntimeError, IOError):
        _LOGGER.error("X720 sensor not detected at 0x%02x", i2c_address)
        return None

    sensor_handler = X720Handler(
        sensor
    )

    sleep(0.5)  # Wait for device to stabilize
    if not sensor_handler.sensor_data.voltage:
        _LOGGER.error("X720 sensor failed to Initialize")
        return None

    return sensor_handler

class X720Handler:
    """X720 sensor working in i2C bus."""

    class SensorData:
        """Sensor data representation."""

        def __init__(self):
            """Initialize the sensor data object."""
            self.voltage = None
            self.capacity = None

    def __init__(
            self, sensor
    ):
        """Initialize the sensor handler."""
        self.sensor_data = X720Handler.SensorData()
        self._sensor = sensor

        self.update(first_read=True)

    def update(self, first_read=False):
        """Read sensor data."""
        if first_read:
            # Attempt first read, it almost always fails first attempt
            self._sensor.get_sensor_data()
        if self._sensor.get_sensor_data():
            self.sensor_data.voltage = self._sensor.data.voltage
            self.sensor_data.capacity = self._sensor.data.capacity

class X720Sensor(Entity):
    """Implementation of the X720 sensor."""

    def __init__(self, x720_client, sensor_type, temp_unit, name):
        """Initialize the sensor."""
        self.client_name = name
        self._name = SENSOR_TYPES[sensor_type][0]
        self.x720_client = x720_client
        self.temp_unit = temp_unit
        self.type = sensor_type
        self._state = None
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]

    @property
    def name(self):
        """Return the name of the sensor."""
        return '{} {}'.format(self.client_name, self._name)

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def icon(self):
        """Return the icon of the sensor"""
        if self.type == SENSOR_VOLTAGE:
            return 'mdi:flash'
        elif self.type == SENSOR_CAPACITY:
          if isinstance(self._state, int) or isinstance(self._state, float):
            if self._state >= 100:
              return 'mdi:battery'
            elif self._state >= 50:
              return 'mdi:battery-50'
            else:
              return 'mdi:battery-alert'
          else:
            return 'mdi:battery-unknown'

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of the sensor."""
        return self._unit_of_measurement

    async def async_update(self):
        """Get the latest data from the X720 and update the states."""
        await self.hass.async_add_job(self.x720_client.update)
        if self.type == SENSOR_VOLTAGE:
            self._state = round(self.x720_client.sensor_data.voltage, 1)
        elif self.type == SENSOR_CAPACITY:
            self._state = round(self.x720_client.sensor_data.capacity, 1)

class FieldData:
    """Structure for storing X720 sensor data."""

    def __init__(self):
        self.status = None
        self.voltage = False
        self.capacity = None

class X720Data:
    """Structure to represent X720 device."""

    def __init__(self):
        self.data = FieldData()

class X720(X720Data):

    def __init__(self, i2c_addr=DEFAULT_I2C_ADDRESS, i2c_device=None):
        X720Data.__init__(self)

        self.i2c_addr = i2c_addr
        self._i2c = i2c_device
        if self._i2c is None:
            import smbus
            self._i2c = smbus.SMBus(1)

        self.get_sensor_data()

    def get_sensor_data(self):
        """Get sensor data.
        Stores data in .data and returns True upon success.
        """

        read = self._i2c.read_word_data(self.i2c_addr, 2)
        swapped = struct.unpack("<H", struct.pack(">H", read))[0]
        self.data.voltage = swapped * 1.25 /1000/16

        read = self._i2c.read_word_data(self.i2c_addr, 4)
        swapped = struct.unpack("<H", struct.pack(">H", read))[0]
        self.data.capacity = swapped/256

        return True