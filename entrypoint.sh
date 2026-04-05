#!/bin/sh
# PUID/PGID support — match container user to host file ownership
# Defaults: 99:100 (nobody:users on Unraid)
PUID=${PUID:-99}
PGID=${PGID:-100}

# Update aeye user/group to match requested IDs
groupmod -o -g "$PGID" aeye 2>/dev/null
usermod -o -u "$PUID" aeye 2>/dev/null

# Fix ownership of app data directory only — NOT the photos directory
# Only run chown if ownership doesn't already match to avoid slow startup
CURRENT_UID=$(stat -c '%u' /app/data 2>/dev/null)
if [ "$CURRENT_UID" != "$PUID" ]; then
    chown -R aeye:aeye /app/data 2>/dev/null || true
fi

exec gosu aeye "$@"
