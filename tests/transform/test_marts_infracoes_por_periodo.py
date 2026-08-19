"""
Testes para a view marts.infracoes_por_periodo (src/transform/006_marts_infracoes_por_periodo.sql).

Cobre:
- agregação correta de total de eventos, motoristas distintos e severidade por dia;
- COUNT(DISTINCT motorista_id) conta o motorista uma vez mesmo com múltiplos
  eventos no mesmo dia;
- eventos em dias diferentes geram linhas separadas;
- evento com data inválida (vira NULL via staging.safe_timestamptz) é excluído
  da mart, nunca aparece sob uma data "genérica";
- mart vazia quando não há eventos.
"""

from __future__ import annotations

from decimal import Decimal


def _evento(**overrides) -> dict:
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


def test_agrega_total_eventos_motoristas_distintos_e_severidade_por_dia(apply_views, insert_raw, fetch_all):
    insert_raw(
        "eventos",
        [
            _evento(event_id="evt-1", driver_id="motorista-a", severity=2, occurred_at="2024-03-01T08:00:00Z"),
            _evento(event_id="evt-2", driver_id="motorista-b", severity=4, occurred_at="2024-03-01T18:00:00Z"),
        ],
    )

    linhas = fetch_all("SELECT * FROM marts.infracoes_por_periodo WHERE data_referencia = '2024-03-01'")
    assert len(linhas) == 1
    linha = linhas[0]
    assert linha["total_eventos"] == 2
    assert linha["motoristas_distintos"] == 2
    assert linha["severidade_media"] == Decimal("3.00")
    assert linha["severidade_maxima"] == 4


def test_mesmo_motorista_varios_eventos_no_dia_conta_motorista_uma_vez(apply_views, insert_raw, fetch_all):
    insert_raw(
        "eventos",
        [
            _evento(event_id="evt-1", driver_id="motorista-a", occurred_at="2024-03-01T08:00:00Z"),
            _evento(event_id="evt-2", driver_id="motorista-a", occurred_at="2024-03-01T18:00:00Z"),
        ],
    )

    linhas = fetch_all("SELECT * FROM marts.infracoes_por_periodo WHERE data_referencia = '2024-03-01'")
    assert len(linhas) == 1
    assert linhas[0]["total_eventos"] == 2
    assert linhas[0]["motoristas_distintos"] == 1


def test_eventos_em_dias_diferentes_geram_linhas_separadas(apply_views, insert_raw, fetch_all):
    insert_raw(
        "eventos",
        [
            _evento(event_id="evt-1", driver_id="motorista-a", occurred_at="2024-03-01T08:00:00Z"),
            _evento(event_id="evt-2", driver_id="motorista-a", occurred_at="2024-03-02T08:00:00Z"),
        ],
    )

    linhas = fetch_all("SELECT * FROM marts.infracoes_por_periodo ORDER BY data_referencia")
    assert len(linhas) == 2
    assert str(linhas[0]["data_referencia"]) == "2024-03-01"
    assert str(linhas[1]["data_referencia"]) == "2024-03-02"


def test_evento_com_data_invalida_e_excluido_da_mart(apply_views, insert_raw, fetch_all):
    insert_raw(
        "eventos",
        [
            _evento(event_id="evt-valido", driver_id="motorista-a", occurred_at="2024-03-01T08:00:00Z"),
            _evento(event_id="evt-data-invalida", driver_id="motorista-b", occurred_at="data-quebrada"),
        ],
    )

    linhas = fetch_all("SELECT * FROM marts.infracoes_por_periodo")
    assert len(linhas) == 1
    assert str(linhas[0]["data_referencia"]) == "2024-03-01"
    assert linhas[0]["total_eventos"] == 1


def test_mart_vazia_quando_nao_ha_eventos(apply_views, fetch_all):
    linhas = fetch_all("SELECT * FROM marts.infracoes_por_periodo")
    assert linhas == []