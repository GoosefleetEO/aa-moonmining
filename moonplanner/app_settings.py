from django.conf import settings

MOONPLANNER_VOLUME_PER_MONTH = getattr(
    settings, 
    'MOONPLANNER_VOLUME_PER_MONTH', 
    14557923
)

MOONPLANNER_REPROCESSING_YIELD = getattr(
    settings, 
    'MOONPLANNER_VOLUME_PER_MONTH', 
    0.7
)
