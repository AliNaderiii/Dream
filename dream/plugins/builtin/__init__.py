"""Standard built-in plugins for Dream Assistant."""

from dream.plugins.builtin.calendar_calc import CalendarCalcPlugin
from dream.plugins.builtin.currency import CurrencyPlugin
from dream.plugins.builtin.weather import WeatherPlugin

__all__ = [
    "WeatherPlugin",
    "CurrencyPlugin",
    "CalendarCalcPlugin",
]
