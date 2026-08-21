"""
Testes de reconciliação entre staging.eventos e as marts derivadas dela.

Cobre o requisito de "contagem" do Módulo 7.1: para cada mart, a
reconciliação é feita executando, contra staging.eventos/staging.motoristas,
uma query independente que espelha o mesmo JOIN/GROUP BY da mart (não um
dicionário de valores fixados a mão) - se o JOIN da view for alterado (ex.:
LEFT JOIN virar INNER JOIN, perdendo eventos sem motorista cadastrado), a
reconciliação diverge e o teste falha. Um segundo assert, com valores
conferidos manualmente, ancora que as duas queries não estão erradas do
mesmo jeito. Deduplicação por chave natural já é coberta nos testes de
staging (test_eventos.py, test_motoristas.py, test_de_para_regional.py) e
não é repetida aqui.

Depende de staging.eventos, staging.motoristas e staging.de_para_regional
(001-003) já aplicadas - feito pela fixture `apply_views`.
"""

from __future__ import annotations

from datetime import date


def _evento(**overrides) -> dict:
    """Payload padrão de um evento (raw.eventos), sobrescrevível via kwargs."""
    base = {
        "event_id": "evt-0001",
        "driver_id": "11111111-1111-1111-1111-111111111111",
        "driver_code": "DRV-0001",
        "vehicle_plate": "ABC1D23",
        "event_type": "EXCESSO_VELOCIDADE",
        "event_description": "Velocidade acima do limite",
        "severity": 3,
        "occurred_at": "2024-03-15T10:30:00Z",
        "speed_kmh": 92.5,
        "latitude": -23.55052,
        "longitude": -46.633308,
    }
    base.update(overrides)
    return base


def _motorista(**overrides) -> dict:
    """Payload padrão de um motorista (raw.motoristas), sobrescrevível via kwargs."""
    base = {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "João da Silva",
        "cpf": "12345678900",
        "registry_id": "MAT0001",
        "phone_numbers": ["11999990000"],
        "active": True,
        "driver_code": "DRV-0001",
        "license": {
            "number": "CNH-0001",
            "category": "B",
            "expiration_date": "2030-01-01",
        },
        "groups": [],
    }
    base.update(overrides)
    return base


def _de_para(**overrides) -> dict:
    """Payload padrão de uma linha de de-para regional, sobrescrevível via kwargs."""
    base = {
        "matricula": "MAT0001",
        "nome": "João da Silva",
        "regional": "Sudeste",
        "centro_custo": "CC-100",
        "email": "joao@example.com",
    }
    base.update(overrides)
    return base


def test_reconciliacao_eventos_por_regional_staging_vs_mart(apply_views, insert_raw, fetch_all):
    """
    Recalcula (regional, tipo_evento) -> total_eventos diretamente de
    staging.eventos + staging.motoristas (mesmo JOIN da mart) e compara
    contra o que marts.eventos_por_regional de fato retorna.
    """
    insert_raw(
        "motoristas",
        [
            _motorista(id="motorista-sudeste", registry_id="MAT0001"),
            _motorista(id="motorista-sul", registry_id="MAT0002"),
        ],
    )
    insert_raw(
        "de_para_regional",
        [
            _de_para(matricula="MAT0001", regional="Sudeste"),
            _de_para(matricula="MAT0002", regional="Sul"),
        ],
    )
    insert_raw(
        "eventos",
        [
            _evento(event_id="evt-1", driver_id="motorista-sudeste", event_type="EXCESSO_VELOCIDADE"),
            _evento(event_id="evt-2", driver_id="motorista-sudeste", event_type="EXCESSO_VELOCIDADE"),
            _evento(event_id="evt-3", driver_id="motorista-sul", event_type="EXCESSO_VELOCIDADE"),
            _evento(event_id="evt-4", driver_id="motorista-sul", event_type="USO_CELULAR"),
            _evento(event_id="evt-5", driver_id="motorista-inexistente", event_type="FRENAGEM_BRUSCA"),
        ],
    )

    reconciliado = fetch_all(
        """
        SELECT
            COALESCE(m.regional, 'SEM REGIONAL') AS regional,
            e.tipo_evento,
            COUNT(*) AS total_eventos
        FROM staging.eventos e
        LEFT JOIN staging.motoristas m ON m.motorista_id = e.motorista_id
        GROUP BY COALESCE(m.regional, 'SEM REGIONAL'), e.tipo_evento
        """
    )
    esperado = {(linha["regional"], linha["tipo_evento"]): linha["total_eventos"] for linha in reconciliado}

    linhas_mart = fetch_all("SELECT regional, tipo_evento, total_eventos FROM marts.eventos_por_regional")
    obtido = {(linha["regional"], linha["tipo_evento"]): linha["total_eventos"] for linha in linhas_mart}

    assert obtido == esperado
    assert obtido == {
        ("Sudeste", "EXCESSO_VELOCIDADE"): 2,
        ("Sul", "EXCESSO_VELOCIDADE"): 1,
        ("Sul", "USO_CELULAR"): 1,
        ("SEM REGIONAL", "FRENAGEM_BRUSCA"): 1,
    }
    assert len(linhas_mart) == len(obtido), "há chave (regional, tipo_evento) duplicada na mart"


def test_reconciliacao_infracoes_por_motorista_staging_vs_mart(apply_views, insert_raw, fetch_all):
    """
    Recalcula motorista_id -> total_eventos diretamente de staging.eventos e
    compara contra o que marts.infracoes_por_motorista de fato retorna.
    """
    insert_raw(
        "motoristas",
        [
            _motorista(id="motorista-a", registry_id="MAT0001"),
            _motorista(id="motorista-b", registry_id="MAT0002"),
        ],
    )
    insert_raw(
        "eventos",
        [
            _evento(event_id="evt-1", driver_id="motorista-a"),
            _evento(event_id="evt-2", driver_id="motorista-a"),
            _evento(event_id="evt-3", driver_id="motorista-b"),
            _evento(event_id="evt-4", driver_id="motorista-inexistente"),
        ],
    )

    reconciliado = fetch_all(
        """
        SELECT e.motorista_id, COUNT(*) AS total_eventos
        FROM staging.eventos e
        LEFT JOIN staging.motoristas m ON m.motorista_id = e.motorista_id
        GROUP BY e.motorista_id
        """
    )
    esperado = {linha["motorista_id"]: linha["total_eventos"] for linha in reconciliado}

    linhas_mart = fetch_all("SELECT motorista_id, total_eventos FROM marts.infracoes_por_motorista")
    obtido = {linha["motorista_id"]: linha["total_eventos"] for linha in linhas_mart}

    assert obtido == esperado
    assert obtido == {"motorista-a": 2, "motorista-b": 1, "motorista-inexistente": 1}
    assert len(linhas_mart) == len(obtido), "há motorista_id duplicado na mart"


def test_reconciliacao_infracoes_por_periodo_staging_vs_mart(apply_views, insert_raw, fetch_all):
    """
    Recalcula data_referencia -> total_eventos diretamente de
    staging.eventos (filtrada por ocorrido_em IS NOT NULL) e compara contra
    o que marts.infracoes_por_periodo de fato retorna.
    """
    insert_raw(
        "eventos",
        [
            _evento(event_id="evt-1", occurred_at="2024-03-01T08:00:00Z"),
            _evento(event_id="evt-2", occurred_at="2024-03-01T20:00:00Z"),
            _evento(event_id="evt-3", occurred_at="2024-03-02T08:00:00Z"),
            _evento(event_id="evt-4", occurred_at=None),
        ],
    )

    reconciliado = fetch_all(
        """
        SELECT date_trunc('day', ocorrido_em)::date AS data_referencia, COUNT(*) AS total_eventos
        FROM staging.eventos
        WHERE ocorrido_em IS NOT NULL
        GROUP BY date_trunc('day', ocorrido_em)::date
        """
    )
    esperado = {linha["data_referencia"]: linha["total_eventos"] for linha in reconciliado}

    linhas_mart = fetch_all("SELECT data_referencia, total_eventos FROM marts.infracoes_por_periodo")
    obtido = {linha["data_referencia"]: linha["total_eventos"] for linha in linhas_mart}

    assert obtido == esperado
    assert obtido == {date(2024, 3, 1): 2, date(2024, 3, 2): 1}
    assert len(linhas_mart) == len(obtido), "há data_referencia duplicada na mart"


def test_marts_ficam_vazias_quando_nao_ha_eventos(apply_views, fetch_all):
    """As três marts derivadas de staging.eventos devem ficar vazias quando não há eventos."""
    for tabela in ("eventos_por_regional", "infracoes_por_motorista", "infracoes_por_periodo"):
        total = fetch_all(f"SELECT COUNT(*) AS total FROM marts.{tabela}")[0]["total"]
        assert total == 0