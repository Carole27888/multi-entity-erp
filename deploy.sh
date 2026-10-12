#!/usr/bin/env bash
# Deploy on a Passenger/cPanel host.
# Usage: ./deploy.sh   (run from the project root with the virtualenv active)
set -euo pipefail
cd "$(dirname "$0")"
export DJANGO_SETTINGS_MODULE=config.settings.prod

pip install -r requirements.txt
# Migrations are not committed (see .gitignore); generate them from the models on this server.
python manage.py makemigrations --noinput
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py check --deploy

# Bump PWA_VERSION so installed apps fetch the new service worker and assets.
NEW_VERSION="$(date +%Y%m%d%H%M%S)"
if [ -f .env ] && grep -q '^PWA_VERSION=' .env; then
  sed -i "s/^PWA_VERSION=.*/PWA_VERSION=${NEW_VERSION}/" .env
else
  echo "PWA_VERSION=${NEW_VERSION}" >> .env
fi

mkdir -p tmp
touch tmp/restart.txt
echo "Deployed. PWA_VERSION=${NEW_VERSION}. Passenger restart requested."
