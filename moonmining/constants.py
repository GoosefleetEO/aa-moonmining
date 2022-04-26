from enum import IntEnum

# EVE IDs


class EveCategoryId(IntEnum):
    ASTEROID = 25


class EveGroupId(IntEnum):
    MOON = 8
    REFINERY = 1406
    UBIQUITOUS_MOON_ASTEROIDS = 1884
    COMMON_MOON_ASTEROIDS = 1920
    UNCOMMON_MOON_ASTEROIDS = 1921
    RARE_MOON_ASTEROIDS = 1922
    EXCEPTIONAL_MOON_ASTEROIDS = 1923


class EveTypeId(IntEnum):
    MOON = 14


class EveDogmaAttributeId(IntEnum):
    ORE_QUALITY = 2699


DATETIME_FORMAT = "%Y-%b-%d %H:%M"
DATE_FORMAT = "%Y-%b-%d"
VALUE_DIVIDER = 1_000_000_000


class IconSize(IntEnum):
    SMALL = 32
    MEDIUM = 64
