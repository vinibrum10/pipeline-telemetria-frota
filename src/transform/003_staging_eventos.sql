CREATE OR REPLACE VIEW staging.eventos AS
WITH deduplicado AS (
    SELECT
        payload,
        ROW_NUMBER() OVER (
            PARTITION BY payload->>'event_id'
            ORDER BY loaded_at DESC
        ) AS ordem
    FROM raw.eventos
)
SELECT
    payload->>'event_id'                     AS evento_id,
    payload->>'driver_id'                    AS motorista_id,
    payload->>'driver_code'                  AS codigo_motorista,
    payload->>'vehicle_plate'                AS placa_veiculo,
    payload->>'event_type'                   AS tipo_evento,
    payload->>'event_description'            AS descricao_evento,
    (payload->>'severity')::int              AS severidade,
    (payload->>'occurred_at')::timestamptz   AS ocorrido_em,
    (payload->>'speed_kmh')::numeric         AS velocidade_kmh,
    (payload->>'latitude')::numeric          AS latitude,
    (payload->>'longitude')::numeric         AS longitude
FROM deduplicado
WHERE ordem = 1;