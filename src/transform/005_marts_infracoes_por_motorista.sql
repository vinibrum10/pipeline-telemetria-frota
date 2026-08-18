CREATE OR REPLACE VIEW marts.infracoes_por_motorista AS
SELECT
    e.motorista_id,
    COALESCE(m.nome, 'MOTORISTA NAO CADASTRADO') AS nome,
    COALESCE(m.matricula, 'SEM MATRICULA') AS matricula,
    COALESCE(m.regional, 'SEM REGIONAL') AS regional,
    COUNT(*) AS total_eventos,
    ROUND(AVG(e.severidade), 2) AS severidade_media,
    MAX(e.severidade) AS severidade_maxima,
    MIN(e.ocorrido_em) AS primeiro_evento,
    MAX(e.ocorrido_em) AS ultimo_evento
FROM staging.eventos e
LEFT JOIN staging.motoristas m
    ON m.motorista_id = e.motorista_id
GROUP BY
    e.motorista_id,
    COALESCE(m.nome, 'MOTORISTA NAO CADASTRADO'),
    COALESCE(m.matricula, 'SEM MATRICULA'),
    COALESCE(m.regional, 'SEM REGIONAL');