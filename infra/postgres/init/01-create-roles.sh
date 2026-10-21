#!/bin/bash
set -euo pipefail

echo ">>> Creating restricted roles for database '${POSTGRES_DB}'"

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" <<-EOSQL
    -- 1. Роль для миграций: владелец схемы, может делать DDL
    CREATE ROLE migration_user
        LOGIN
        PASSWORD '${MIGRATION_USER_PASSWORD}'
        NOSUPERUSER NOCREATEDB NOCREATEROLE;

    -- 2. Роль для приложения: только DML, без DDL
    CREATE ROLE app_user
        LOGIN
        PASSWORD '${APP_USER_PASSWORD}'
        NOSUPERUSER NOCREATEDB NOCREATEROLE;

    -- 3. Отдельная схема приложения, владельцем которой является migration_user
    CREATE SCHEMA app AUTHORIZATION migration_user;

    -- 4. Роль приложения может подключаться и видеть схему
    GRANT CONNECT ON DATABASE "${POSTGRES_DB}" TO migration_user;
    GRANT CONNECT ON DATABASE "${POSTGRES_DB}" TO app_user;
    GRANT USAGE ON SCHEMA app TO app_user;

    -- 5. Права на уже существующие объекты
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO app_user;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO app_user;

    -- 6. Автоматически выдавать права на будущие таблицы/последовательности
    ALTER DEFAULT PRIVILEGES FOR ROLE migration_user IN SCHEMA app
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
    ALTER DEFAULT PRIVILEGES FOR ROLE migration_user IN SCHEMA app
        GRANT USAGE, SELECT ON SEQUENCES TO app_user;

    -- 7. Отзываем опасные права у PUBLIC
    REVOKE ALL ON DATABASE "${POSTGRES_DB}" FROM PUBLIC;
    REVOKE CREATE ON SCHEMA public FROM PUBLIC;
EOSQL

echo ">>> Roles 'migration_user' and 'app_user' created"