CREATE OR REPLACE VIEW staging.motoristas AS
WITH deduplicado AS (
    SELECT
        payload,
        ROW_NUMBER() OVER (
            PARTITION BY payload->>'id'
            ORDER BY loaded_at DESC
        ) AS ordem
    FROM raw.motoristas
)
SELECT
    d.payload->>'id'                                          AS motorista_id,
    d.payload->>'driver_code'                                 AS codigo_motorista,
    d.payload->>'registry_id'                                 AS matricula,
    trim(regexp_replace(d.payload->>'name', '\s+', ' ', 'g')) AS nome,
    d.payload->>'cpf'                                         AS cpf,
    (d.payload->>'active')::boolean                           AS ativo,
    d.payload->'license'->>'category'                         AS cnh_categoria,
    (d.payload->'license'->>'expiration_date')::date          AS cnh_validade,
    dp.regional,
    dp.centro_custo
FROM deduplicado d
LEFT JOIN staging.de_para_regional dp
    ON dp.matricula = d.payload->>'registry_id'
WHERE d.ordem = 1;
