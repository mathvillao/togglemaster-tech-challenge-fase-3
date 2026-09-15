CREATE DATABASE flags_db;
CREATE DATABASE targeting_db;

\connect flags_db
\i /scripts/flag-init.sql

\connect targeting_db
\i /scripts/targeting-init.sql