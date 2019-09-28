from django.conf import settings

# defaults
MOONSTUFF_CONFIG = {
    'total_volume_per_month': 14557923,
    'reprocessing_yield': 0.7    
}

def get_config() -> dict:    
    """returns the current config"""
    config = MOONSTUFF_CONFIG
    
    # override with dict from settings if it exists
    try:
        for k, v in settings.MOONSTUFF_CONFIG.items():
            config[k] = v
    except AttributeError:
        # config not defined in settings
        pass
            
    return config