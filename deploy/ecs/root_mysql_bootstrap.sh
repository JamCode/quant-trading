#!/usr/bin/env bash
# 在 ECS 上以 root 执行（本机: ssh root@ECS 'bash -s' < deploy/ecs/root_mysql_bootstrap.sh）
set -euo pipefail

WANGHAN_HOME="/home/wanghan"
SCHEMA="${WANGHAN_HOME}/quant-trading/schema/mysql/001_init.sql"
ENV_FILE="${WANGHAN_HOME}/quant-trading/deploy/ecs/fund-stack.env"

systemctl enable --now mysqld

mysql < "$SCHEMA"

PASS="$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)"
mysql <<SQL
DROP USER IF EXISTS 'fund_app'@'localhost';
CREATE USER 'fund_app'@'localhost' IDENTIFIED BY '${PASS}';
GRANT ALL PRIVILEGES ON fund_svc.* TO 'fund_app'@'localhost';
FLUSH PRIVILEGES;
SQL

umask 077
mkdir -p "$(dirname "$ENV_FILE")"
cat > "$ENV_FILE" <<EOF
DATABASE_URL=mysql+pymysql://fund_app:${PASS}@127.0.0.1:3306/fund_svc
FUND_URL_PREFIX=/quant-funds
FUND_WEB_HOST=127.0.0.1
FUND_WEB_PORT=8010
CRAWLER_CRON_HOUR=2
CRAWLER_CRON_MINUTE=0
FUND_SYNC_INCLUDE_DAILY=1
FUND_DETAIL_CACHE_HOURS=24
EOF
chown wanghan:wanghan "$ENV_FILE"
chmod 600 "$ENV_FILE"
echo "root_mysql_bootstrap: ok (fund-stack.env written)"
