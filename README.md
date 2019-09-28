# Moonplanner

Moonplanner is a plugin for [AllianceAuth](https://gitlab.com/allianceauth/allianceauth) to allow alliances to better manage moons and their
extraction schedules.

**IMPORTANT**

- This is a heavy modified fork of the original "moonstuff" app from colcrunch. It's not migration compatible with the original due to major changes in the data model. Data migration from moonstuff is possible, but would require a custom data migration script.

- This app requires [allianceauth-evesde](https://gitlab.com/ErikKalkoken/allianceauth-evesde) to be installed to work.

WIP !!

## Features

Features inherited from moonstuf:

- Manage moon extractions

- Add moons via surveys

- Browse list of scanned moons

- Detail view of moons

Additional features:

- Filter by solar system and region in moon list

- Show estimated monthly income for moons and ores

- Optimized to handle thousands of moons with good performance

- Open multiple moon details at the same time

## Installation

Install the project from git to your allianceauth venv.

```bash
source /path/to/auth/venv/activate
pip install git+https://gitlab.com/colcrunch/aa-moonplanner
```

The add it to your `INSTALLED-APPS` in `local.py`.
```python
INSTALLED_APPS+=[
        'moonplanner',
    ]
```

Then run migrations and restart your supervisor processes.

### Task Schedule
Add the following to the end of your `local.py`:
```python
CELERYBEAT_SCHEDULE['run_moonplanner_data_import'] = {
    'task': 'moonplanner.tasks.import_data',
    'schedule': crontab(minute='30'),
}
```

Alternatively, you can go to the django admin page and add the task at `[your auth url]/admin/django_celery_beat/periodictask/` 

## Permissions

The permissions for this plugin are rather straight forward.

* `moonplanner.access_moonplanner` - This is access permission, users without this permission will be unable to access the plugin.
* `moonplanner.add_resource` - This permission allows users to upload moon scan data.
* `moonplanner.add_extractionevent` - This permission is allows users to add their tokens to be pulled from when checking for new extraction events. 
 