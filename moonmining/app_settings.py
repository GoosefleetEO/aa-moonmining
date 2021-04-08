from app_utils.django import clean_setting

# Number of hours an extractions that has passed its ready time is still shown
# on the upcoming extractions tab
MOONMINING_COMPLETED_EXTRACTIONS_HOURS_UNTIL_STALE = clean_setting(
    "MOONMINING_COMPLETED_EXTRACTIONS_HOURS_UNTIL_STALE", 12
)

# Reprocessing yield used for calculating all values
MOONMINING_REPROCESSING_YIELD = clean_setting("MOONMINING_REPROCESSING_YIELD", 0.82)

# Total ore volume per month used for calculating moon values.
MOONMINING_VOLUME_PER_MONTH = clean_setting("MOONMINING_VOLUME_PER_MONTH", 14557923)

# whether admins will get notifications about import events like
# when someone adds a structure owner
MOONMINING_ADMIN_NOTIFICATIONS_ENABLED = clean_setting(
    "STRUCTURES_ADMIN_NOTIFICATIONS_ENABLED", True
)
