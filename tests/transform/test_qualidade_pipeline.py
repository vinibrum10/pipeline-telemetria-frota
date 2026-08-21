"""
Testes de reconciliação entre staging.eventos e as marts derivadas dela.

Cobre o requisito de "contagem" do Módulo 7.1: garante que os LEFT JOINs e
GROUP BYs usados nas marts (004, 005, 006) não perdem, duplicam nem
reagrupam eventos incorretamente. A reconciliação é feita por chave de
grupo (não só pela soma global), porque um evento atribuído ao grupo
errado por um bug de JOIN manteria a soma total igual - só comparar por
chave pega esse caso. Deduplicação por chave natural já é coberta nos
testes de staging (test_eventos.py, test_motoristas.py,
test_de_para_regional.py) e não é repetida aqui.

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


def test_contagem_por_grupo_bate_com_staging_eventos_evita_grupo_trocado(apply_views, insert_raw, fetch_all):
    """
    Reconcilia staging.eventos e marts.eventos_por_regional por grupo
    (regional, tipo_evento), não só pelo total global - um bug no LEFT JOIN
    que jogasse um evento pro grupo errado manteria a soma global igual.
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
        ],
    )

    esperado = {
        ("Sudeste", "EXCESSO_VELOCIDADE"): 2,
        ("Sul", "EXCESSO_VELOCIDADE"): 1,
        ("Sul", "USO_CELULAR"): 1,
    }

    linhas = fetch_all("SELECT regional, tipo_evento, total_eventos FROM marts.eventos_por_regional")
    obtido = {(linha["regional"], linha["tipo_evento"]): linha["total_eventos"] for linha in linhas}

    assert obtido == esperado
    assert len(linhas) == len(obtido), "há chave (regional, tipo_evento) duplicada na mart"


def test_contagem_por_motorista_bate_com_staging_eventos_evita_grupo_trocado(apply_views, insert_raw, fetch_all):
    """
    Reconcilia staging.eventos e marts.infracoes_por_motorista por
    motorista_id, não só pelo total global.
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
        ],
    )

    esperado = {"motorista-a": 2, "motorista-b": 1}
    linhas = fetch_all("SELECT motorista_id, total_eventos FROM marts.infracoes_por_motorista")
    obtido = {linha["motorista_id"]: linha["total_eventos"] for linha in linhas}

    assert obtido == esperado
    assert len(linhas) == len(obtido), "há motorista_id duplicado na mart"


def test_contagem_por_periodo_bate_com_staging_eventos_evita_dia_trocado(apply_views, insert_raw, fetch_all):
    """
    Reconcilia staging.eventos (filtrada por ocorrido_em IS NOT NULL) e
    marts.infracoes_por_periodo por data_referencia, não só pelo total
    global.
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

    esperado = {date(2024, 3, 1): 2, date(2024, 3, 2): 1}
    linhas = fetch_all("SELECT data_referencia, total_eventos FROM marts.infracoes_por_periodo")
    obtido = {linha["data_referencia"]: linha["total_eventos"] for linha in linhas}

    assert obtido == esperado
    assert len(linhas) == len(obtido), "há data_referencia duplicada na mart"


def test_marts_ficam_vazias_quando_nao_ha_eventos(apply_views, fetch_all):
    """As três marts derivadas de staging.eventos devem ficar vazias quando não há eventos."""
    for tabela in ("eventos_por_regional", "infracoes_por_motorista", "infracoes_por_periodo"):
        total = fetch_all(f"SELECT COUNT(*) AS total FROM marts.{tabela}")[0]["total"]
        assert total == 0