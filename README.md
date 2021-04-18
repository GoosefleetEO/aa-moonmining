# Moon Mining

An Alliance Auth app for tracking moon extractions and scouting new moons.

[![release](https://img.shields.io/pypi/v/aa-moonmining?label=release)](https://pypi.org/project/aa-moonmining/)
[![python](https://img.shields.io/pypi/pyversions/aa-moonmining)](https://pypi.org/project/aa-moonmining/)
[![django](https://img.shields.io/pypi/djversions/aa-moonmining?label=django)](https://pypi.org/project/aa-moonmining/)
[![pipeline](https://gitlab.com/ErikKalkoken/aa-moonmining/badges/master/pipeline.svg)](https://gitlab.com/ErikKalkoken/aa-moonmining/-/pipelines)
[![codecov](https://codecov.io/gl/ErikKalkoken/aa-moonmining/branch/master/graph/badge.svg?token=3tY1AOIp4B)](https://codecov.io/gl/ErikKalkoken/aa-moonmining)
[![license](https://img.shields.io/badge/license-MIT-green)](https://gitlab.com/ErikKalkoken/aa-moonmining/-/blob/master/LICENSE)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![chat](https://img.shields.io/discord/790364535294132234)](https://discord.gg/zmh52wnfvM)

## Contents

- [Features](#features)
- [Installation](#installation)
- [Permissions](#permissions)
- [Settings](#settings)
- [Management Commands](#management-commands)
- [FAQ](#faq)
- [Change Log](CHANGELOG.md)

## Features

- Upload survey scans and research your moon database.
- Monitor active extractions from your refineries.
- Automatic value estimates for all moons and extractions.
- Mining ledger per extraction
- Reports (e.g. potential total income of all owned moons)
- Tool for mass importing moon scans from external sources

## Highlights

### Research your moon database

Build your own moon database from survey inputs and find the best moons for you. The moon rarity class and value are automatically calculated from your survey input.

![moons](https://i.imgur.com/kxjuPNN.png)

See the exact ore makeup of this moon on the details page.

![moons](https://i.imgur.com/qrLGHZb.png)

Note that you can also see on this list which moons you already own. In addition an extraction button is visible, when an extraction is active for a particular moon.

### Manage extractions

After you added your corporation you can see which moons you own and see upcoming and past extractions:

![moons](https://i.imgur.com/earsLke.png)

You can also review the extraction details, incl. which ore qualities you got.

![moons](https://i.imgur.com/mt9eyNN.png)

### Mining ledger

See what has been minded from an extraction in the mining ledger:

![Mining Ledger](https://i.imgur.com/mQen9Y8.png)

### Reports

Check out the reporting section for detail reports on your operation, e.g. Breakdown by corporation and moon of your potential total gross moon income per months:

![moons](https://i.imgur.com/JBDPTtB.png)

> **Note**<br>All ore compositions and ISK values shown on these screenshots are fake.

## Installation

### Preconditions

1. Moon Mining is a plugin for Alliance Auth. If you don't have Alliance Auth running already, please install it first before proceeding. (see the official [AA installation guide](https://allianceauth.readthedocs.io/en/latest/installation/auth/allianceauth/) for details)

2. Moon Mining needs the app [django-eveuniverse](https://gitlab.com/ErikKalkoken/django-eveuniverse) to function. Please make sure it is installed, before before continuing.

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
CELERYBEAT_SCHEDULE['moonmining_run_report_updates'] = {
    'task': 'moonmining.tasks.run_report_updates',
    'schedule': crontab(hour='*/2'),
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

Restart your supervisor services for Auth.

### Step 4 - Load ores from ESI

Please run the following management command to load all ores from ESI. This has to be done once only.

```bash
python manage.py moonmining_load_eve
```

Please wait until the loading is complete before continuing.

> **Note**<br>You can monitor the progress on by looking at how many tasks are running on the dashboard.

### Step 5 - Update EVE Online API Application

Update the Eve Online API app used for authentication in your AA installation to include the following scopes:

- `esi-industry.read_corporation_mining.v1`
- `esi-universe.read_structures.v1`
- `esi-characters.read_notifications.v1`

### Step 6 - Setup permissions

Finally you want to setup permission to define which users / groups will have access to which parts of the app. Check out [permissions](#permissions) for details.

Congratulations! You are now ready to use Moon Mining!

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
`MOONMINING_COMPLETED_EXTRACTIONS_HOURS_UNTIL_STALE`| Number of hours an extractions that has passed its ready time is still shown on the upcoming extractions tab. | `12`
`MOONMINING_REPROCESSING_YIELD`| Reprocessing yield used for calculating all values | `0.82`
`MOONMINING_VOLUME_PER_MONTH`| Total ore volume per month used for calculating moon values. | `14557923`

## Management Commands

The following management commands are available to perform administrative tasks:

> **Hint**:<br>Run any command with `--help` to see all options

Name | Description
-- | --
`moonmining_calculate_all`| Calculate all properties for moons and extractions.
`moonmining_load_eve`| Pre-loads data required for this app from ESI to improve app performance.
`moonmining_import_moons`| Import moons from an CSV file. Example:<br>`moon_id,ore_type_id,amount`<br>`40161708,45506,0.19`

## FAQ

### Extractions

- Q: Why does the tool not show values and ores for all my extractions?
- A: Unfortunately, the Eve Online API does only provide basic information for extractions. Additional information like the list of ores are retrieved by trying to match moon mining notifications to extractions. However, that process it not 100% reliable. For example the API returns the latest notifications only, so  notifications for extractions that have been setup weeks ago might no longer be available.

### Prices

- Q: How are the prices and values of ores calculated?
- A: The price of an ore is calculated as the sum of prices for it's refined minerals. Since most people are refining their ores before selling them this approach is a better measure of the real value of ores then the direct price.
The prices themselves are the average item prices across new Eden (not Jita prices), which are the same prices that the in-game client is using to show estimates.
