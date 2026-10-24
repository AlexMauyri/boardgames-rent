#!/bin/sh
set -e

# Путь к генерируемому ACL-файлу
ACL_FILE="/run/redis/users.acl"

# 1. Создаём базовый ACL-файл: отключаем пользователя default
echo "user default off nopass nocommands" > "$ACL_FILE"

# 2. Добавляем пользователя для приложения (backend)
if [ -n "$REDIS_APP_USER" ] && [ -n "$REDIS_APP_PASSWORD" ]; then
  echo "user ${REDIS_APP_USER} on >${REDIS_APP_PASSWORD} ~* &* +@all -@dangerous -CONFIG -DEBUG -SHUTDOWN -FLUSHALL -FLUSHDB" >> "$ACL_FILE"
fi

# 3. (Опционально) Добавляем администратора, если заданы переменные
if [ -n "$REDIS_ADMIN_USER" ] && [ -n "$REDIS_ADMIN_PASSWORD" ]; then
  echo "user ${REDIS_ADMIN_USER} on >${REDIS_ADMIN_PASSWORD} ~* &* +@all" >> "$ACL_FILE"
fi

# 4. Запускаем оригинальный entrypoint Redis с нашим конфигом
exec /usr/local/bin/docker-entrypoint.sh redis-server /usr/local/etc/redis/redis.conf