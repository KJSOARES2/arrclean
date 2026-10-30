#!/usr/bin/env bash
set -e

PUID=${PUID:-1000}
PGID=${PGID:-1000}

# Configure Timezone
if [ -n "$TZ" ] && [ -f "/usr/share/zoneinfo/$TZ" ]; then
    ln -snf "/usr/share/zoneinfo/$TZ" /etc/localtime
    echo "$TZ" > /etc/timezone
fi

# Create group if not existing
if ! getent group arrclean >/dev/null; then
    groupadd -g "$PGID" arrclean 2>/dev/null || true
fi

# Create user if not existing
if ! id -u arrclean >/dev/null 2>&1; then
    useradd -u "$PUID" -g "$PGID" -d /app -s /bin/bash -M arrclean 2>/dev/null || true
fi

# Ensure data directory exists and has correct permissions
mkdir -p /app/data
chown -R "$PUID:$PGID" /app/data /app 2>/dev/null || true

echo "--------------------------------------------------------"
echo "Starting ArrClean Media Manager"
echo "UID: $PUID | GID: $PGID | TZ: ${TZ:-UTC}"
echo "--------------------------------------------------------"

# Execute command as specified user
if [ "$PUID" -eq 0 ]; then
    exec "$@"
elif command -v gosu >/dev/null 2>&1; then
    exec gosu "$PUID:$PGID" "$@"
else
    exec su -s /bin/bash arrclean -c 'exec "$@"' -- "$@"
fi
