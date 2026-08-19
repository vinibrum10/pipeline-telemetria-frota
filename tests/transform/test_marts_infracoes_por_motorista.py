"""
Testes para a view marts.infracoes_por_motorista (src/transform/005_marts_infracoes_por_motorista.sql).

Cobre:
- agregação correta de contagem, severidade e datas por motorista;
- motorista sem regional no de-para aparece com regional 'SEM REGIONAL';
- evento sem motorista correspondente em staging.motoristas não é descartado -
  aparece como 'MOTORISTA NAO CADASTRADO' / 'SEM MATRICULA' / 'SEM REGIONAL';
- mart vazia quando não há eventos.
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
        "license": {"number": "CNH-0001", "category": "B", "expiration_date": "2030-01-01"},
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


def test_agrega_total_eventos_severidade_e_datas_por_motorista(apply_views, insert_raw, fetch_all):
    insert_raw("motoristas", [_motorista(id="motorista-joao", registry_id="MAT0001")])
    insert_raw("de_para_regional", [_de_para(matricula="MAT0001", regional="Sudeste")])
    insert_raw(
        "eventos",
        [
            _evento(event_id="evt-1", driver_id="motorista-joao", severity=2, occurred_at="2024-03-01T08:00:00Z"),
            _evento(event_id="evt-2", driver_id="motorista-joao", severity=4, occurred_at="2024-03-10T08:00:00Z"),
        ],
    )

    linhas = fetch_all("SELECT * FROM marts.infracoes_por_motorista WHERE motorista_id = 'motorista-joao'")
    assert len(linhas) == 1
    linha = linhas[0]
    assert linha["nome"] == "João da Silva"
    assert linha["matricula"] == "MAT0001"
    assert linha["regional"] == "Sudeste"
    assert linha["total_eventos"] == 2
    assert linha["severidade_media"] == Decimal("3.00")
    assert linha["severidade_maxima"] == 4
    assert str(linha["primeiro_evento"]) == "2024-03-01 08:00:00+00:00"
    assert str(linha["ultimo_evento"]) == "2024-03-10 08:00:00+00:00"


def test_motorista_sem_regional_no_de_para_aparece_como_sem_regional(apply_views, insert_raw, fetch_all):
    insert_raw("motoristas", [_motorista(id="motorista-sem-regional", registry_id="MAT-INEXISTENTE")])
    insert_raw("eventos", [_evento(event_id="evt-sr", driver_id="motorista-sem-regional", event_type="USO_CELULAR")])

    linhas = fetch_all("SELECT * FROM marts.infracoes_por_motorista WHERE motorista_id = 'motorista-sem-regional'")
    assert len(linhas) == 1
    assert linhas[0]["regional"] == "SEM REGIONAL"
    assert linhas[0]["total_eventos"] == 1


def test_evento_sem_motorista_correspondente_nao_e_descartado(apply_views, insert_raw, fetch_all):
    insert_raw("eventos", [_evento(event_id="evt-orfao", driver_id="motorista-inexistente", event_type="FRENAGEM_BRUSCA")])

    linhas = fetch_all("SELECT * FROM marts.infracoes_por_motorista WHERE motorista_id = 'motorista-inexistente'")
    assert len(linhas) == 1
    assert linhas[0]["nome"] == "MOTORISTA NAO CADASTRADO"
    assert linhas[0]["matricula"] == "SEM MATRICULA"
    assert linhas[0]["regional"] == "SEM REGIONAL"


def test_mart_vazia_quando_nao_ha_eventos(apply_views, fetch_all):
    linhas = fetch_all("SELECT * FROM marts.infracoes_por_motorista")
    assert linhas == []