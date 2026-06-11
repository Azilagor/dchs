-- PostgreSQL bootstrap script for production/staging
-- Usage example:
-- psql -U postgres -f scripts/create_postgres_db.sql

-- Change these values before running if needed.
\set app_db mchs_directory
\set app_user mchs_user
\set app_password strong_password_change_me

DO
$$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = :'app_user') THEN
        EXECUTE format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'app_user', :'app_password');
    END IF;
END
$$;

DO
$$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = :'app_db') THEN
        EXECUTE format('CREATE DATABASE %I OWNER %I', :'app_db', :'app_user');
    END IF;
END
$$;

\connect :app_db

ALTER DATABASE :app_db OWNER TO :app_user;
GRANT ALL PRIVILEGES ON DATABASE :app_db TO :app_user;

GRANT ALL ON SCHEMA public TO :app_user;
ALTER SCHEMA public OWNER TO :app_user;

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

ALTER ROLE :app_user SET client_encoding TO 'UTF8';
ALTER ROLE :app_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE :app_user SET timezone TO 'Asia/Qyzylorda';
