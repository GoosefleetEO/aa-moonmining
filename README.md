# Moonstuff

Moonstuff is a plugin for [AllianceAuth](https://gitlab.com/allianceauth/allianceauth) to allow alliances to better manage moons and their
extraction schedules.

## Installation

Install the project from git to your allianceauth venv.

```bash
source /path/to/auth/venv/activate
pip install git+https://gitlab.com/colcrunch/aa-moonstuff
```

The add it to your `INSTALLED-APPS` in `local.py`.
```python
INSTALLED_APPS+=[
        'moonstuff',
    ]
```

Then run migrations and restart your supervisor processes.

## Permissions

The permissions for this plugin are rather straight forward.

* `moonstuff.view_moonstuff` - This is access permission, users without this permission will be unable to access the plugin.
* `moonstuff.add_resource` - This permission allows users to upload moon scan data.
* `moonstuff.add_extractionevent` - This permission is allows users to update the list of upcomming extractions. 

#### Note: There is currently no logic to check for extraction events automatically. 