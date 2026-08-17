"""
Testes para a view marts.eventos_por_regional (src/transform/004_marts_eventos_por_regional.sql).

Cobre:
- agregação correta de contagem/severidade por regional e tipo de evento;
- motorista sem regional no de-para aparece como 'SEM REGIONAL', nunca é
  descartado silenciosamente (COALESCE sobre o LEFT JOIN);
- evento sem motorista correspondente em staging.motoristas também não é
  descartado - o LEFT JOIN entre eventos e motoristas deve preservar o evento;
- mart vazia quando não há eventos.

Depende de staging.eventos e staging.motoristas (002 e 003) já estarem aplicadas -
isso é feito pela fixture `apply_views`, que roda todos os arquivos de
src/transform/ em ordem.
"""

from __future__ import annotations

from decimal import Decimal


def _motorista(**overrides) -> dict:
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
    base = {
        "matricula": "MAT0001",
        "nome": "João da Silva",
        "regional": "Sudeste",
        "centro_custo": "CC-100",
        "email": "joao@example.com",
    }
    base.update(overrides)
    return base


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


def test_agrega_contagem_e_severidade_por_regional_e_tipo_evento(apply_views, insert_raw, fetch_all):
    insert_raw("motoristas", [_motorista(id="motorista-sudeste", registry_id="MAT0001")])
    insert_raw("de_para_regional", [_de_para(matricula="MAT0001", regional="Sudeste")])
    insert_raw(
        "eventos",
        [
            _evento(
                event_id="evt-1",
                driver_id="motorista-sudeste",
                event_type="EXCESSO_VELOCIDADE",
                severity=2,
                occurred_at="2024-03-01T08:00:00Z",
            ),
            _evento(
                event_id="evt-2",
                driver_id="motorista-sudeste",
                event_type="EXCESSO_VELOCIDADE",
                severity=4,
                occurred_at="2024-03-10T08:00:00Z",
            ),
        ],
    )

    linhas = fetch_all(
        "SELECT * FROM marts.eventos_por_regional WHERE regional = 'Sudeste' AND tipo_evento = 'EXCESSO_VELOCIDADE'"
    )
    assert len(linhas) == 1
    linha = linhas[0]
    assert linha["total_eventos"] == 2
    assert linha["severidade_media"] == Decimal("3.00")
    assert linha["severidade_maxima"] == 4
    assert str(linha["primeiro_evento"]) == "2024-03-01 08:00:00+00:00"
    assert str(linha["ultimo_evento"]) == "2024-03-10 08:00:00+00:00"


def test_motorista_sem_regional_no_de_para_aparece_como_sem_regional(apply_views, insert_raw, fetch_all):
    insert_raw("motoristas", [_motorista(id="motorista-sem-regional", registry_id="MAT-INEXISTENTE")])
    # Nenhum registro em de_para_regional para MAT-INEXISTENTE - o motorista existe
    # em staging.motoristas, mas com regional NULL.
    insert_raw(
        "eventos",
        [_evento(event_id="evt-sem-regional", driver_id="motorista-sem-regional", event_type="USO_CELULAR")],
    )

    linhas = fetch_all(
        "SELECT * FROM marts.eventos_por_regional WHERE tipo_evento = 'USO_CELULAR'"
    )
    assert len(linhas) == 1
    assert linhas[0]["regional"] == "SEM REGIONAL"
    assert linhas[0]["total_eventos"] == 1


def test_evento_sem_motorista_correspondente_nao_e_descartado(apply_views, insert_raw, fetch_all):
    # Nenhum motorista com esse driver_id existe em staging.motoristas - o LEFT JOIN
    # deve preservar o evento, com regional caindo em 'SEM REGIONAL'.
    insert_raw(
        "eventos",
        [_evento(event_id="evt-orfao", driver_id="motorista-inexistente", event_type="FRENAGEM_BRUSCA")],
    )

    linhas = fetch_all("SELECT * FROM marts.eventos_por_regional WHERE tipo_evento = 'FRENAGEM_BRUSCA'")
    assert len(linhas) == 1
    assert linhas[0]["regional"] == "SEM REGIONAL"
    assert linhas[0]["total_eventos"] == 1


def test_mart_vazia_quando_nao_ha_eventos(apply_views, fetch_all):
    linhas = fetch_all("SELECT * FROM marts.eventos_por_regional")
    assert linhas == []
