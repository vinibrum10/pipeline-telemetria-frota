CREATE OR REPLACE VIEW staging.de_para_regional AS
WITH deduplicado AS (
    SELECT
        payload,
        ROW_NUMBER() OVER (
            PARTITION BY payload->>'matricula'
            ORDER BY loaded_at DESC
        ) AS ordem
    FROM raw.de_para_regional
)
SELECT
    payload->>'matricula'                    AS matricula,
    NULLIF(trim(payload->>'regional'), '')   AS regional,
    payload->>'centro_custo'                 AS centro_custo,
    lower(trim(payload->>'email'))           AS email
FROM deduplicado
WHERE ordem = 1;
