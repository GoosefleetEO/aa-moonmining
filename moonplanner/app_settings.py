from django.conf import settings

# Number of hours an extractions that has passed its ready time is still shown
# on the upcoming extractions tab
MOONPLANNER_EXTRACTIONS_HOURS_UNTIL_STALE = getattr(
    settings, "MOONPLANNER_EXTRACTIONS_HOURS_UNTIL_STALE", 12
)
# Reprocessing yield used for calculating all values
MOONPLANNER_REPROCESSING_YIELD = getattr(
    settings, "MOONPLANNER_REPROCESSING_YIELD", 0.7
)
# report as delayed when corporations have not been updated since x minutes
MOONPLANNER_UPDATES_MINUTES_UNTIL_DELAYED = getattr(
    settings, "MOONPLANNER_UPDATES_MINUTES_UNTIL_DELAYED", 90
)

# Total ore volume per month used for calculating moon values.
MOONPLANNER_VOLUME_PER_MONTH = getattr(
    settings, "MOONPLANNER_VOLUME_PER_MONTH", 14557923
)
