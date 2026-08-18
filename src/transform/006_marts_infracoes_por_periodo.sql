CREATE OR REPLACE VIEW marts.infracoes_por_periodo AS
SELECT
    date_trunc('day', e.ocorrido_em)::date AS data_referencia,
    COUNT(*) AS total_eventos,
    COUNT(DISTINCT e.motorista_id) AS motoristas_distintos,
    ROUND(AVG(e.severidade), 2) AS severidade_media,
    MAX(e.severidade) AS severidade_maxima
FROM staging.eventos e
WHERE e.ocorrido_em IS NOT NULL
GROUP BY date_trunc('day', e.ocorrido_em)::date
ORDER BY data_referencia;