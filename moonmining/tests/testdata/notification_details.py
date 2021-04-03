"""Helper script to get moon mining notifications incl. text into a structured format"""

import json
from copy import copy
from pathlib import Path

import yaml

file = Path(__file__).parent / "esi.json"
with file.open("r", encoding="utf-8") as fp:
    esi_data = json.load(fp)

notifications_raw = esi_data["Character"]["get_characters_character_id_notifications"][
    "1005"
]
notifications = dict()
for notif_raw in notifications_raw:
    notif = copy(notif_raw)
    del notif["text"]
    del notif["is_read"]
    notif["details"] = yaml.safe_load(notif_raw["text"])
    notifications[notif_raw["type"]] = notif

file = Path(__file__).parent / "notifications_full.json"
with file.open("w", encoding="utf-8") as fp:
    json.dump(notifications, fp, indent=4, sort_keys=True)
