from django.conf import settings

MOONPLANNER_VOLUME_PER_MONTH = getattr(
    settings, "MOONPLANNER_VOLUME_PER_MONTH", 14557923
)

MOONPLANNER_REPROCESSING_YIELD = getattr(
    settings, "MOONPLANNER_REPROCESSING_YIELD", 0.7
)

# Number of hours an extractions that has passed its ready time is still shown
# on the upcoming extractions tab
MOONPLANNER_EXTRACTIONS_HOURS_UNTIL_STALE = getattr(
    settings, "MOONPLANNER_EXTRACTIONS_HOURS_UNTIL_STALE", 12
)
