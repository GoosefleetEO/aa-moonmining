# Moon Planner

An Alliance Auth app for tracking moon extractions and scouting new moons.

[![release](https://img.shields.io/pypi/v/aa-moonmining?label=release)](https://pypi.org/project/aa-moonmining/)
[![python](https://img.shields.io/pypi/pyversions/aa-moonmining)](https://pypi.org/project/aa-moonmining/)
[![django](https://img.shields.io/pypi/djversions/aa-moonmining?label=django)](https://pypi.org/project/aa-moonmining/)
[![pipeline](https://gitlab.com/ErikKalkoken/aa-moonmining/badges/master/pipeline.svg)](https://gitlab.com/ErikKalkoken/aa-moonmining/-/pipelines)
[![codecov](https://codecov.io/gl/ErikKalkoken/aa-moonmining/branch/master/graph/badge.svg?token=QHMCUAFZBV)](https://codecov.io/gl/ErikKalkoken/aa-moonmining)
[![license](https://img.shields.io/badge/license-MIT-green)](https://gitlab.com/ErikKalkoken/aa-moonmining/-/blob/master/LICENSE)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![chat](https://img.shields.io/discord/790364535294132234)](https://discord.gg/zmh52wnfvM)

## Contents

- [Features](#features)
- [Installation](#installation)
- [Permissions](#permissions)
- [Settings](#settings)
- [Change Log](CHANGELOG.md)

## Features

- Upload survey scans and research your own moon database.
- Monitor ongoing extractions from your refineries.
- Automatic value estimates for all moons and extractions.
- See reports for your potential total income

## Highlights

### Research your moon database

Build your own moon database from survey inputs and find the best moons for you. The moon rarity class and value are automatically calculated from your survey input.

![moons](https://i.imgur.com/usZcEmC.png)

See the exact ore makeup of this moon on the details page.

![moons](https://i.imgur.com/olSr4mh.png)

### Manage extractions

After you added your corporation you can see which moons you own and see upcoming and past extractions:

![moons](https://i.imgur.com/fJ6rTvq.png)

You can also review the extraction details, incl. which ore qualities you got.

![moons](https://i.imgur.com/ZGH7eWL.png)

### Reports

Check out the reporting section for detail reports on your operation, e.g. Breakdown by corporation and moon of your potential total gross moon income per months:

![moons](https://i.imgur.com/JBDPTtB.png)

> **Note**<br>All ore compositions and ISK values shown on this screenshot are fake.

## Installation

### Preconditions

1. Moon Planner is a plugin for Alliance Auth. If you don't have Alliance Auth running already, please install it first before proceeding. (see the official [AA installation guide](https://allianceauth.readthedocs.io/en/latest/installation/auth/allianceauth/) for details)

2. Moon Planner needs the app [django-eveuniverse](https://gitlab.com/ErikKalkoken/django-eveuniverse) to function. Please make sure it is installed, before before continuing.

### Step 1 - Install app

Make sure you are in the virtual environment (venv) of your Alliance Auth installation. Then install the newest release from PyPI:

```bash
pip install aa-moonmining
```

### Step 2 - Configure Auth settings

Configure your Auth settings (`local.py`) as follows:

- Add `'moonmining'` to `INSTALLED_APPS`
- Add below lines to your settings file:

```python
CELERYBEAT_SCHEDULE['moonmining_run_regular_updates'] = {
    'task': 'moonmining.tasks.run_regular_updates',
    'schedule': crontab(minute='*/10'),
}
CELERYBEAT_SCHEDULE['moonmining_run_value_updates'] = {
 'task': 'moonmining.tasks.run_calculated_properties_update',
 'schedule': crontab(minute=30, hour=3)
}

> **Hint**: The value updates are supposed to run once a day during off hours. Feel free to adjust to timing according to your timezone.
```

- Optional: Add additional settings if you want to change any defaults. See [Settings](#settings) for the full list.

### Step 3 - Finalize App installation

Run migrations & copy static files

```bash
python manage.py migrate
python manage.py collectstatic
```

Restart your supervisor services for Auth

### Step 4 - Update EVE Online API Application

Update the Eve Online API app used for authentication in your AA installation to include the following scopes:

- `esi-industry.read_corporation_mining.v1`
- `esi-universe.read_structures.v1`
- `esi-characters.read_notifications.v1`

### Step 5 - Setup permissions

Finally you want to setup permission to define which users / groups will have access to which parts of the app. Check out [permissions](#permissions) for details.

Congratulations you are now ready to use Moon Planner!

## Permissions

Here is an overview of all permissions:

Name  | Description
-- | --
`moonmining.basic_access` | This is access permission, users without this permission will be unable to access the plugin.
`moonmining.upload_moon_scan` | This permission allows users to upload moon scan data.
`moonmining.extractions_access` | User can access extractions and view owned moons
`moonmining.view_all_moons` | User can view all moons in the database
`moonmining.add_refinery_owner` | This permission is allows users to add their tokens to be pulled from when checking for new extraction events.

## Settings

Here is a list of available settings for this app. They can be configured by adding them to your AA settings file (`local.py`).

Note that all settings are optional and the app will use the documented default settings if they are not used.

Name | Description | Default
-- | -- | --
`MOONMINING_EXTRACTIONS_HOURS_UNTIL_STALE`| Number of hours an extractions that has passed its ready time is still shown on the upcoming extractions tab. | `12`
`MOONMINING_REPROCESSING_YIELD`| Reprocessing yield used for calculating all values | `0.82`
`MOONMINING_VOLUME_PER_MONTH`| Total ore volume per month used for calculating moon values. | `14557923`
