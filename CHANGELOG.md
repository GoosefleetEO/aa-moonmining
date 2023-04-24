# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased] - yyyy-mm-dd

### Fixed

- Admin page with ore prices breaks when some prices are missing
- Various typos

## [1.8.2] - 2023-03-12

### Fixed

- Admin page with ore prices crashed when prices have not been loaded yet

## [1.8.1] - 2023-01-31

### Fixed

- Applied workaround for chained task priority bug

## [1.8.0] - 2022-12-13

### Changed

- Remove support for Python 3.7 and add support for Python 3.10
- Update swagger.json to 1.12

## [1.7.3] - 2022-07-21

### Changed

- Moved some test factories to app_utils

## [1.7.2] - 2022-06-18

### Fixed

- Add missing swagger spec file

## [1.7.1] - 2022-06-17

### Changed

- Deploy wheel to PyPI
- Switch to local swagger spec file

## [1.7.0] - 2022-05-03

### Added

- Ability to manually update moon products from extractions
- New setting `MOONMINING_OVERWRITE_SURVEYS_WITH_ESTIMATES` to turn on overwriting any moon products incl. surveys

### Changed

- When updating a moon's products with an estimate the app will no longer overwrite existing surveys. But estimates are still generated for owned moons, without surveys.

## [1.6.1] - 2022-04-28

**Update notes**:<br>Due to the previous bug (#18) the calculated moon values may be inaccurate. We recommend to run the action "update selected owners from ESI" for all active ownwer on the admin site, which will also update moon values from the last extractions.

### Added

- Show duration on extraction details page

### Fixed

- Automatically updated moon product percentages are sometimes off (#18)
- Show "ESTIMATED" as "survey submitter" for extimated moon products

### Changed

- Setting `MOONMINING_VOLUME_PER_MONTH` replaced by new settings: `MOONMINING_VOLUME_PER_DAY` and `MOONMINING_DAYS_PER_MONTH`

## [1.6.0] - 2022-04-26

### Added

- Ability to use calculated refined pricing instead of normal ore prices (#16)
- Ability to add custom labels to moons and use them to filter moons (#17)
- Report showing current ore prices

### Changed

- Default reprocessing yield set to 85 %
- Changed moon tables to server-side rendering for significant performance boost (#15)

## [1.5.0] - 2022-04-21

### Added

- Already owned moons no longer need to be scanned in order to get it's ore composition for the value calculation. The ore composition is automatically updated when a new extraction is started.

### Changed

- Now uses the **average price** for ores instead of an estimated price based on it's refined ores. This means that the prices shown in the app are now exactly the same as the prices shown on the Eve client, e.g. price estimates shown when scheduling a new extraction.
- Now showing full unit prices in ISK, to improve comparibility between ore types

### Fixed

- Monthly volume used for moon value calucaltions adjusted to changed game mechanics (#13)

## [1.4.0] - 2022-04-20

### Added

- Add drop-down filters for constellation to extractions (#12)
- Add drop-down filters for rarity to extractions (#12)
- Add drop-down filters for constellation to moons (#12)

## [1.3.1] - 2022-03-02

### Fixed

- Tests having sessions fail with Django 4

## [1.3.0] - 2022-03-01

### Changed

- Drop support for Python 3.6
- Drop support for Django 3.1
- Establish compatibility with Django 4.0

## [1.2.2] - 2022-01-02

### Fixed

- Does not show values for member mining of previous year (#11)

## [1.2.1] - 2022-01-02

### Added

- Mining ledger records on admin site
- Now shows if an extraction has a ledger on admin site

### Changed

- Improved page performance for admin site / Refineries

### Fixed

- Mining ledger is shown even when the ledger is empty

## [1.2.0] - 2021-11-22

### Added

- Restrict access to mining ledger with permission (#8)

### Changed

- Improved view tests

### Fixed

- Access to extractions was possible with "view_all_moons" permission only, now user always needs "extractions_access" permission

## [1.1.0] - 2021-11-03

### Added

- New report showing number of uploaded moons by mains

### Changed

- Added tests for AA 2.9 / Django 3.2

## [1.0.2] - 2021-07-23

### Fixed

- Fix attempt: Expression contains mixed types: FloatField, IntegerField. You must set output_field (#6)

## [1.0.1] - 2021-06-26

### Changed

- Now checks if ESI is available before starting any update tasks. This should eliminate ESI exceptions during the daily downtime.
- Improved admin error message if refinery updates fail

## [1.0.0] - 2021-06-24

### Changed

- Improved error handling and admin notifications for invalid tokens and ESI errors

### Fixed

- Refinery update aborts when one refinery can not be accessed

## [1.0.0b4] - 2021-05-19

### Added

- Show volume totals in header, row totals for price and volume and % totals for characters

### Fixed

- Refinery update fails when there are multiple refineries next to the same moon (#5)

### Changed

## [1.0.0b3] - 2021-04-24

### Added

- Tool for exporting moons from moonstuff v1 (for details see management commands in README)
- Mining ledger now includes page showing totals per character

### Changed

- Added name of refineries to the extractions list ([#1](https://gitlab.com/ErikKalkoken/aa-moonmining/-/issues/1))
- Reduced page load time for mining ledger

## [1.0.0b2] - 2021-04-18

> **Note for 1.0.0a3**<br>This alpha release includes a migration reset. Please make sure to migrate to zero BEFORE installing this new version.

### Added

- Release of new version based on eveuniverse

## [0.1.12] - 2020-10-09

### Changed

- Add more tests
- Added menu item for moon detail page

### Fixed

- Fixed more Font Awesome icons to work with v5

## [0.1.11] - 2020-10-08

### Changed

- Added black formatting and linter
- Added CI tests for Django 3

### Fixed

- Icon is now shown again
- Fixes for Django 3
- Better error handling and more reliable feedback when survey scan fails

## [0.1.10] - 2020-03-04

### Fixed

- Incorrect permission checks

## [0.1.9] - 2020-03-03

### Changed

- Added fault tolerance to moon income update task for missing types

## [0.1.8] - 2020-03-03

### Changed

- Squashed migrations incl. old migrations

## [0.1.7] - 2020-03-03

### Changed

- Added automated testing with tox and Gitlab runner
