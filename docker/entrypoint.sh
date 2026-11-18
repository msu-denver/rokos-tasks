#!/bin/sh
# File: entrypoint.sh
# Description: Container entrypoint script that runs migrations and starts web.
# Author(s): Tyler Black

set -e

alembic upgrade head
exec "$@"
