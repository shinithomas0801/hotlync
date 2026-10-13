#!/bin/bash
set -euo pipefail

cd /workspace/development

if [ ! -d frappe-bench/apps/frappe ]; then
	echo "== bench init =="
	bench init --skip-redis-config-generation --frappe-branch version-16 frappe-bench
fi

cd frappe-bench

bench set-config -g db_host mariadb
bench set-config -g redis_cache redis://redis-cache:6379
bench set-config -g redis_queue redis://redis-queue:6379
bench set-config -g redis_socketio redis://redis-queue:6379

if grep -q redis Procfile; then
	sed -i "/redis/d" Procfile
fi

if [ ! -d apps/erpnext ]; then
	echo "== get erpnext =="
	bench get-app --branch version-16 --resolve-deps erpnext
fi

if [ ! -d apps/hrms ]; then
	echo "== get hrms =="
	bench get-app --branch version-16 https://github.com/frappe/hrms.git
fi

if [ ! -e apps/hotlync ]; then
	ln -s /workspace/hotlync apps/hotlync
fi

if ! grep -qx hotlync sites/apps.txt; then
	tail -c1 sites/apps.txt | read -r _ || echo >> sites/apps.txt
	echo hotlync >> sites/apps.txt
fi

./env/bin/pip install -e apps/hotlync

if [ ! -d sites/development.localhost ]; then
	echo "== new site =="
	bench new-site \
		--db-root-password 123 \
		--admin-password admin \
		--mariadb-user-host-login-scope=% \
		development.localhost
fi

bench use development.localhost

install_if_missing() {
	local app="$1"
	if ! bench --site development.localhost list-apps | awk '{print $1}' | grep -qx "$app"; then
		echo "== install $app =="
		bench --site development.localhost install-app "$app"
	fi
}

install_if_missing erpnext
install_if_missing hrms
install_if_missing hotlync

bench --site development.localhost set-config developer_mode 1
bench --site development.localhost set-config allow_cors "http://127.0.0.1:5173"
bench --site development.localhost clear-cache
bench --site development.localhost migrate
bench --site development.localhost execute hotlync.accommodation.seed.execute

echo "== day 1 bench ready =="
