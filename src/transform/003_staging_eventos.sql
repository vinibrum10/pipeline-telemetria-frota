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
    payload->>'event_id'                              AS evento_id,
    payload->>'driver_id'                              AS motorista_id,
    payload->>'driver_code'                            AS codigo_motorista,
    payload->>'vehicle_plate'                          AS placa_veiculo,
    payload->>'event_type'                             AS tipo_evento,
    payload->>'event_description'                      AS descricao_evento,
    staging.safe_int(payload->>'severity')             AS severidade,
    staging.safe_timestamptz(payload->>'occurred_at')  AS ocorrido_em,
    staging.safe_numeric(payload->>'speed_kmh')        AS velocidade_kmh,
    staging.safe_numeric(payload->>'latitude')         AS latitude,
    staging.safe_numeric(payload->>'longitude')        AS longitude
FROM deduplicado
WHERE ordem = 1;