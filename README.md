# Moon Planner

An Alliance Auth app for tracking moon extractions and scouting new moons.

[![release](https://img.shields.io/pypi/v/aa-moonplanner?label=release)](https://pypi.org/project/aa-moonplanner/)
[![python](https://img.shields.io/pypi/pyversions/aa-moonplanner)](https://pypi.org/project/aa-moonplanner/)
[![django](https://img.shields.io/pypi/djversions/aa-moonplanner?label=django)](https://pypi.org/project/aa-moonplanner/)
[![pipeline](https://gitlab.com/ErikKalkoken/aa-moonplanner/badges/master/pipeline.svg)](https://gitlab.com/ErikKalkoken/aa-moonplanner/-/pipelines)
[![codecov](https://codecov.io/gl/ErikKalkoken/aa-moonplanner/branch/master/graph/badge.svg?token=QHMCUAFZBV)](https://codecov.io/gl/ErikKalkoken/aa-moonplanner)
[![license](https://img.shields.io/badge/license-MIT-green)](https://gitlab.com/ErikKalkoken/aa-moonplanner/-/blob/master/LICENSE)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![chat](https://img.shields.io/discord/790364535294132234)](https://discord.gg/zmh52wnfvM)

## Contents

- [Features](#features)
- [Installation](#installation)
- [Permissions](#permissions)
- [Settings](#settings)
- [Management Commands](#management-commands)
- [Change Log](CHANGELOG.md)

## Features

- Manage moon extractions
- Upload moon surveys
- Browse list of scanned moons
- Detail view of moons
- Filter by solar solar_system and region in moon list
- Show estimated monthly income for moons and ores
- Optimized to handle thousands of moons with good performance
- Open multiple moon detail pages at the same time

> **Note**<br>This is a heavy modified fork of the original [moonstuff](https://gitlab.com/colcrunch/aa-moonstuff) by [colcrunch](https://gitlab.com/colcrunch). It's not migration compatible with the original due to major changes in the data model.

## Installation

### Preconditions

1. Moon Planner is a plugin for Alliance Auth. If you don't have Alliance Auth running already, please install it first before proceeding. (see the official [AA installation guide](https://allianceauth.readthedocs.io/en/latest/installation/auth/allianceauth/) for details)

2. Moon Planner needs the app [django-eveuniverse](https://gitlab.com/ErikKalkoken/django-eveuniverse) to function. Please make sure it is installed, before before continuing.

### Step 1 - Install app

Make sure you are in the virtual environment (venv) of your Alliance Auth installation. Then install the newest release from PyPI:

```bash
pip install aa-memberaudit
```

### Step 2 - Configure Auth settings

Configure your Auth settings (`local.py`) as follows:

- Add `'moonplanner'` to `INSTALLED_APPS`
- Add below lines to your settings file:

```python
CELERYBEAT_SCHEDULE['moonplanner_run_updates'] = {
    'task': 'memberaudit.tasks.update_all_mining_corporations',
    'schedule': crontab(minute='0', minute='*/30'),
}
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

### Step 5 - Load Eve Universe map data

In order to be able to select solar systems and ships types for trackers you need to load that data from ESI once. If you already have run those commands previously you can skip this step.

Load Eve Online map:

```bash
python manage.py eveuniverse_load_data map
```

```bash
python manage.py memberaudit_load_eve
```

You may want to wait until the loading is complete before continuing.

> **Hint**: These command will spawn a thousands of tasks. One easy way to monitor the progress is to watch the number of tasks shown on the Dashboard.

### Step 6 - Setup permissions

Finally you want to setup permission to define which users / groups will have access to which parts of the app. Check out [permissions](#permissions) for details.

Congratulations you are now ready to use Moon Planner!

## Permissions

Here is an overview of all permissions:

Name  | Description
-- | --
`moonplanner.access_moonplanner` | This is access permission, users without this permission will be unable to access the plugin.
`moonplanner.upload_moon_scan` | This permission allows users to upload moon scan data.
`moonplanner.access_our_moons` | User gets access all moons that have refineries
`moonplanner.access_all_moons` | User gets access to all moons in the database
`moonplanner.add_mining_corporation` | This permission is allows users to add their tokens to be pulled from when checking for new extraction events.

## Settings

Here is a list of available settings for this app. They can be configured by adding them to your AA settings file (`local.py`).

Note that all settings are optional and the app will use the documented default settings if they are not used.

Name | Description | Default
-- | -- | --
`MOONPLANNER_EXTRACTIONS_HOURS_UNTIL_STALE`| Number of hours an extractions that has passed its ready time is still shown on the upcoming extractions tab. | `12`
`MOONPLANNER_REPROCESSING_YIELD`| Reprocessing yield used for calculating all values | `0.7`
`MOONPLANNER_VOLUME_PER_MONTH`| Total ore volume per month used for calculating moon values. | `14557923`

## Management Commands

The following management commands are available to perform administrative tasks:

> **Hint**:<br>Run any command with `--help` to see all options

### moonplanner_load_eve

Pre-loads data required for this app from ESI to improve app performance.
