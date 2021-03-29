from django.conf import settings

# Number of hours an extractions that has passed its ready time is still shown
# on the upcoming extractions tab
MOONMINING_EXTRACTIONS_HOURS_UNTIL_STALE = getattr(
    settings, "MOONMINING_EXTRACTIONS_HOURS_UNTIL_STALE", 12
)
# Reprocessing yield used for calculating all values
MOONMINING_REPROCESSING_YIELD = getattr(settings, "MOONMINING_REPROCESSING_YIELD", 0.7)
# Total ore volume per month used for calculating moon values.
MOONMINING_VOLUME_PER_MONTH = getattr(settings, "MOONMINING_VOLUME_PER_MONTH", 14557923)
