# Staff Accommodation Management System

SAMS is the temporary name for this staff accommodation system. The Frappe app is the local proof of concept on ERPNext.

## Remaining Technical Identifiers

The installed app id stays `hotlync`. Changing it would move the Python package, the Frappe app record, API routes, and the files already mounted into the bench. These identifiers stay until a separate migration:

- Python package and Frappe app name: `hotlync` (`pyproject.toml` `name`, `hooks.py` `app_name`)
- API methods: `hotlync.api.*`, including the React calls that use those paths
- Permission hook paths and test modules under `hotlync.accommodation`
- Bench install path `apps/hotlync` and the Docker mount `../hotlync:/workspace/hotlync`
- Local logins and other addresses on `@hotlync.local`
- Database savepoint names such as `hotlync_report` and `hotlync_transfer`
- The constant `SAMS_ROLES` is the in-code name for the three accommodation roles. It is not a DocType or an API.

A Company row or a property address created by an earlier seed is not rewritten. The seed text now says SAMS only when those rows are created for the first time.
