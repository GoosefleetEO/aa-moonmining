# Moonplanner

Moonplanner is a plugin for [AllianceAuth](https://gitlab.com/allianceauth/allianceauth) to allow alliances to manage moon extractions and to build and research a moon database.

**IMPORTANT**

- This is a heavy modified fork of the original [moonstuff](https://gitlab.com/colcrunch/aa-moonstuff) by [colcrunch](https://gitlab.com/colcrunch). It's not migration compatible with the original due to major changes in the data model. ( Data migration from **moonstuff** would be possible with a custom data migration script.)

- This app requires [allianceauth-evesde](https://gitlab.com/ErikKalkoken/allianceauth-evesde) to be installed and fully updated to work.

WIP !!

## Features

Features inherited from moonstuf:

- Manage moon extractions
- Add moons via surveys
- Browse list of scanned moons
- Detail view of moons

Additional features:

- Filter by solar solar_system and region in moon list
- Show estimated monthly income for moons and ores
- Optimized to handle thousands of moons with good performance
- Open multiple moon detail pages at the same time

## Installation

Make sure these ESI scopes are part of your EVE app:

- esi-industry.read_corporation_mining.v1
- esi-universe.read_structures.v1
- esi-characters.read_notifications.v1

Install the project from git to your allianceauth venv.

```bash
source /path/to/auth/venv/activate
pip install git+https://gitlab.com/ErikKalkoken/aa-moonplanner.git
```

Theb add it to your `INSTALLED-APPS` in `local.py`.

```python
INSTALLED_APPS+=[
        'moonplanner',
    ]
```

Add the following to the end of your `local.py`:

```python
CELERYBEAT_SCHEDULE['run_moonplanner_data_import'] = {
    'task': 'moonplanner.tasks.import_data',
    'schedule': crontab(minute='30'),
}
```

Finally run migrations and restart your supervisor processes.

## Permissions

Here is an overview of all permissions

Name  | Description
-- | --
`moonplanner.access_moonplanner` | This is access permission, users without this permission will be unable to access the plugin.
`moonplanner.upload_moon_scan` | This permission allows users to upload moon scan data.
`moonplanner.research_moons` | User gets access to all moons in the database
`moonplanner.add_extractionevent` | This permission is allows users to add their tokens to be pulled from when checking for new extraction events.
