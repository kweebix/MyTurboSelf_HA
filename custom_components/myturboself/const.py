"""Constants for the MyTurboSelf integration."""

from datetime import timedelta

from homeassistant.const import Platform

CONF_MANUAL_MEAL_PRICE = "manual_meal_price"
CONF_SKIP_HOLIDAYS = "skip_holidays"
CONF_SKIP_VACATION = "skip_vacation"
CONF_SCHOOL_ZONE = "school_zone"
CONF_MEALS_FRIDAY = "meals_friday"
CONF_MEALS_MONDAY = "meals_monday"
CONF_MEALS_SATURDAY = "meals_saturday"
CONF_MEALS_SUNDAY = "meals_sunday"
CONF_MEALS_THURSDAY = "meals_thursday"
CONF_MEALS_TUESDAY = "meals_tuesday"
CONF_MEALS_WEDNESDAY = "meals_wednesday"
DEFAULT_BASE_URL = "https://espacenumerique.turbo-self.com/"

DOMAIN = "myturboself"
DEFAULT_NAME = "MyTurboSelf"
MANUFACTURER = "TurboSelf"
MODEL = "MyTurboSelf account"
SCAN_INTERVAL = timedelta(minutes=15)
PLATFORMS: list[Platform] = [Platform.SENSOR]

ATTR_CONFIGURED_MEALS_PER_WEEK = "configured_meals_per_week"
ATTR_DATA_SOURCE = "data_source"
ATTR_EFFECTIVE_MEAL_PRICE = "effective_meal_price"
ATTR_LAST_EVENT = "last_event"
ATTR_REMOTE_MEALS_LEFT = "remote_meals_left"
ATTR_SCHEDULE = "schedule"
ATTR_USER_DATA = "user_data"

MEAL_TYPE_BREAKFAST = "breakfast"
MEAL_TYPE_LUNCH = "lunch"
MEAL_TYPE_DINNER = "dinner"

MEAL_TYPES = {
    MEAL_TYPE_BREAKFAST: "Petit-déjeuner",
    MEAL_TYPE_LUNCH: "Midi",
    MEAL_TYPE_DINNER: "Soir",
}

DEFAULT_MANUAL_MEAL_PRICE = 0.0
DEFAULT_WEEKDAY_MEALS: dict[str, list[str]] = {
    CONF_MEALS_MONDAY: [MEAL_TYPE_LUNCH],
    CONF_MEALS_TUESDAY: [MEAL_TYPE_LUNCH],
    CONF_MEALS_WEDNESDAY: [MEAL_TYPE_LUNCH],
    CONF_MEALS_THURSDAY: [MEAL_TYPE_LUNCH],
    CONF_MEALS_FRIDAY: [MEAL_TYPE_LUNCH],
    CONF_MEALS_SATURDAY: [],
    CONF_MEALS_SUNDAY: [],
}

MEAL_DAY_OPTIONS: tuple[str, ...] = (
    CONF_MEALS_MONDAY,
    CONF_MEALS_TUESDAY,
    CONF_MEALS_WEDNESDAY,
    CONF_MEALS_THURSDAY,
    CONF_MEALS_FRIDAY,
    CONF_MEALS_SATURDAY,
    CONF_MEALS_SUNDAY,
)

WEEKDAY_LABELS: dict[int, str] = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}
