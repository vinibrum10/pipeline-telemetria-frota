"""
Testes de reconciliação entre staging.eventos e as marts derivadas dela.

Cobre o requisito de "contagem" do Módulo 7.1: garante que os LEFT JOINs e
GROUP BYs usados nas marts (004, 005, 006) não perdem nem duplicam eventos
silenciosamente. Deduplicação por chave natural já é coberta nos testes de
staging (test_eventos.py, test_motoristas.py, test_de_para_regional.py) e
não é repetida aqui.

Depende de staging.eventos, staging.motoristas e staging.de_para_regional
(001-003) já aplicadas - feito pela fixture `apply_views`.
"""

from __future__ import annotations


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


def test_soma_eventos_por_regional_bate_com_staging_eventos(apply_views, insert_raw, fetch_all):
    insert_raw(
        "eventos",
        [
            _evento(event_id="evt-1", event_type="EXCESSO_VELOCIDADE"),
            _evento(event_id="evt-2", event_type="USO_CELULAR"),
            _evento(event_id="evt-3", event_type="FRENAGEM_BRUSCA", driver_id="motorista-inexistente"),
        ],
    )

    total_staging = fetch_all("SELECT COUNT(*) AS total FROM staging.eventos")[0]["total"]
    total_mart = fetch_all("SELECT SUM(total_eventos) AS total FROM marts.eventos_por_regional")[0]["total"]

    assert total_mart == total_staging == 3


def test_soma_infracoes_por_motorista_bate_com_staging_eventos(apply_views, insert_raw, fetch_all):
    insert_raw(
        "eventos",
        [
            _evento(event_id="evt-1", driver_id="motorista-a"),
            _evento(event_id="evt-2", driver_id="motorista-a"),
            _evento(event_id="evt-3", driver_id="motorista-b"),
        ],
    )

    total_staging = fetch_all("SELECT COUNT(*) AS total FROM staging.eventos")[0]["total"]
    total_mart = fetch_all("SELECT SUM(total_eventos) AS total FROM marts.infracoes_por_motorista")[0]["total"]

    assert total_mart == total_staging == 3


def test_soma_infracoes_por_periodo_bate_com_staging_eventos_com_data(apply_views, insert_raw, fetch_all):
    """
    infracoes_por_periodo filtra `WHERE ocorrido_em IS NOT NULL` - a
    reconciliação aqui é contra staging.eventos já filtrada pela mesma
    condição, não contra o total bruto.
    """
    insert_raw(
        "eventos",
        [
            _evento(event_id="evt-1", occurred_at="2024-03-01T08:00:00Z"),
            _evento(event_id="evt-2", occurred_at="2024-03-02T08:00:00Z"),
            _evento(event_id="evt-3", occurred_at=None),
        ],
    )

    total_staging_com_data = fetch_all(
        "SELECT COUNT(*) AS total FROM staging.eventos WHERE ocorrido_em IS NOT NULL"
    )[0]["total"]
    total_mart = fetch_all("SELECT SUM(total_eventos) AS total FROM marts.infracoes_por_periodo")[0]["total"]

    assert total_mart == total_staging_com_data == 2


def test_marts_ficam_vazias_quando_nao_ha_eventos(apply_views, fetch_all):
    for tabela in ("eventos_por_regional", "infracoes_por_motorista", "infracoes_por_periodo"):
        total = fetch_all(f"SELECT COUNT(*) AS total FROM marts.{tabela}")[0]["total"]
        assert total == 0
