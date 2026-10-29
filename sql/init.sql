-- 처음 기동할 때 한 번만 돈다. 에이전트가 쓸 읽기 전용 역할을 만든다.
CREATE ROLE monitor_ro LOGIN PASSWORD 'monitor_ro';

GRANT CONNECT ON DATABASE monitor TO monitor_ro;
GRANT USAGE ON SCHEMA public TO monitor_ro;

ALTER DEFAULT PRIVILEGES FOR ROLE monitor IN SCHEMA public
    GRANT SELECT ON TABLES TO monitor_ro;
