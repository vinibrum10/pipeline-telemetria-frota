-- Roda automaticamente na primeira inicialização do container Postgres
-- (só na primeira vez — se o volume postgres_data já existir, isso não roda de novo).

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;

COMMENT ON SCHEMA raw IS 'Cópia fiel do que a fonte devolveu, sem tratamento. Nunca editar.';
COMMENT ON SCHEMA staging IS 'Dados limpos: tipados, deduplicados, nomes padronizados.';
COMMENT ON SCHEMA marts IS 'Modelo de negócio pronto para consumo. Os painéis leem só daqui.';