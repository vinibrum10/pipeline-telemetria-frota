CREATE OR REPLACE VIEW marts.eventos_por_regional AS
SELECT
    COALESCE(m.regional, 'SEM REGIONAL')  AS regional,
    e.tipo_evento,
    COUNT(*)                              AS total_eventos,
    ROUND(AVG(e.severidade), 2)           AS severidade_media,
    MAX(e.severidade)                     AS severidade_maxima,
    MIN(e.ocorrido_em)                    AS primeiro_evento,
    MAX(e.ocorrido_em)                    AS ultimo_evento
FROM staging.eventos e
LEFT JOIN staging.motoristas m
    ON m.motorista_id = e.motorista_id
GROUP BY
    COALESCE(m.regional, 'SEM REGIONAL'),
    e.tipo_evento;
