from app_utils.app_settings import clean_setting

MOONMINING_COMPLETED_EXTRACTIONS_HOURS_UNTIL_STALE = clean_setting(
    "MOONMINING_COMPLETED_EXTRACTIONS_HOURS_UNTIL_STALE", 12
)
"""Number of hours an extractions that has passed its ready time is still shown
on the upcoming extractions tab.
"""

MOONMINING_REPROCESSING_YIELD = clean_setting("MOONMINING_REPROCESSING_YIELD", 0.85)
"""Reprocessing yield used for calculating reprocess prices."""

MOONMINING_USE_REPROCESS_PRICING = clean_setting(
    "MOONMINING_USE_REPROCESS_PRICING", False
)
"""Whether to calculate prices from reprocessed materials or not.
Will use direct ore prices when switched off.
"""

MOONMINING_VOLUME_PER_DAY = clean_setting("MOONMINING_VOLUME_PER_DAY", 960_400)
MOONMINING_DAYS_PER_MONTH = clean_setting("MOONMINING_DAYS_PER_MONTH", 30.4)
MOONMINING_VOLUME_PER_MONTH = MOONMINING_VOLUME_PER_DAY * MOONMINING_DAYS_PER_MONTH
"""Total ore volume per month used for calculating moon values."""

MOONMINING_ADMIN_NOTIFICATIONS_ENABLED = clean_setting(
    "MOONMINING_ADMIN_NOTIFICATIONS_ENABLED", True
)
"""Whether admins will get notifications about important events like
when someone adds a new owner.
"""

MOONMINING_OVERWRITE_SURVEYS_WITH_ESTIMATES = clean_setting(
    "MOONMINING_OVERWRITE_SURVEYS_WITH_ESTIMATES", False
)
"""whether uploaded survey are automatically overwritten by product estimates from
extractions to keep the moon values current."""
