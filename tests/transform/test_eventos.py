"""
Testes para a view staging.eventos (src/transform/003_staging_eventos.sql).

Cobre:
- extração e passagem direta de campos textuais;
- casts de tipo: severity -> int, occurred_at -> timestamptz, speed_kmh/latitude/
  longitude -> numeric;
- speed_kmh ausente/nulo não deve quebrar a view (campo documentado como opcional);
- valores numéricos negativos (longitude) são preservados;
- deduplicação por event_id, mantendo o payload de loaded_at mais recente;
- ausência de linha quando raw está vazio.
"""

from __future__ import annotations

from datetime import datetime, timezone
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


def test_view_expoe_colunas_esperadas(apply_views, insert_raw, fetch_all):
    insert_raw("eventos", [_evento()])

    linhas = fetch_all("SELECT * FROM staging.eventos WHERE evento_id = 'evt-0001'")
    assert len(linhas) == 1
    assert set(linhas[0].keys()) == {
        "evento_id",
        "motorista_id",
        "codigo_motorista",
        "placa_veiculo",
        "tipo_evento",
        "descricao_evento",
        "severidade",
        "ocorrido_em",
        "velocidade_kmh",
        "latitude",
        "longitude",
    }


def test_campos_textuais_passam_direto(apply_views, insert_raw, fetch_all):
    insert_raw(
        "eventos",
        [
            _evento(
                event_id="evt-textos",
                driver_id="drv-id-1",
                driver_code="DRV-9999",
                vehicle_plate="XYZ9Z99",
                event_type="FRENAGEM_BRUSCA",
                event_description="Frenagem acima do esperado",
            )
        ],
    )

    linhas = fetch_all(
        "SELECT motorista_id, codigo_motorista, placa_veiculo, tipo_evento, descricao_evento "
        "FROM staging.eventos WHERE evento_id = 'evt-textos'"
    )
    linha = linhas[0]
    assert linha["motorista_id"] == "drv-id-1"
    assert linha["codigo_motorista"] == "DRV-9999"
    assert linha["placa_veiculo"] == "XYZ9Z99"
    assert linha["tipo_evento"] == "FRENAGEM_BRUSCA"
    assert linha["descricao_evento"] == "Frenagem acima do esperado"


def test_severidade_e_convertida_para_inteiro(apply_views, insert_raw, fetch_all):
    insert_raw("eventos", [_evento(event_id="evt-sev", severity=5)])

    linhas = fetch_all("SELECT severidade FROM staging.eventos WHERE evento_id = 'evt-sev'")
    assert linhas[0]["severidade"] == 5
    assert isinstance(linhas[0]["severidade"], int)


def test_ocorrido_em_e_convertido_para_timestamptz(apply_views, insert_raw, fetch_all):
    insert_raw("eventos", [_evento(event_id="evt-ts", occurred_at="2024-03-15T10:30:00Z")])

    linhas = fetch_all("SELECT ocorrido_em FROM staging.eventos WHERE evento_id = 'evt-ts'")
    assert linhas[0]["ocorrido_em"] == datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc)


def test_velocidade_ausente_resulta_em_null(apply_views, insert_raw, fetch_all):
    evento = _evento(event_id="evt-sem-velocidade")
    del evento["speed_kmh"]
    insert_raw("eventos", [evento])

    linhas = fetch_all("SELECT velocidade_kmh FROM staging.eventos WHERE evento_id = 'evt-sem-velocidade'")
    assert linhas[0]["velocidade_kmh"] is None


def test_velocidade_nula_no_payload_resulta_em_null(apply_views, insert_raw, fetch_all):
    insert_raw("eventos", [_evento(event_id="evt-velocidade-null", speed_kmh=None)])

    linhas = fetch_all("SELECT velocidade_kmh FROM staging.eventos WHERE evento_id = 'evt-velocidade-null'")
    assert linhas[0]["velocidade_kmh"] is None


def test_latitude_e_longitude_negativas_sao_preservadas(apply_views, insert_raw, fetch_all):
    insert_raw(
        "eventos",
        [_evento(event_id="evt-geo", latitude=-23.55052, longitude=-46.633308)],
    )

    linhas = fetch_all("SELECT latitude, longitude FROM staging.eventos WHERE evento_id = 'evt-geo'")
    assert linhas[0]["latitude"] == Decimal("-23.55052")
    assert linhas[0]["longitude"] == Decimal("-46.633308")


def test_deduplica_por_event_id_mantendo_loaded_at_mais_recente(apply_views, insert_raw, fetch_all):
    insert_raw(
        "eventos",
        [_evento(event_id="evt-dup", severity=1, event_type="USO_CELULAR")],
        loaded_at="2024-01-01T00:00:00Z",
    )
    insert_raw(
        "eventos",
        [_evento(event_id="evt-dup", severity=4, event_type="EXCESSO_VELOCIDADE")],
        loaded_at="2024-06-01T00:00:00Z",
    )

    linhas = fetch_all("SELECT severidade, tipo_evento FROM staging.eventos WHERE evento_id = 'evt-dup'")
    assert len(linhas) == 1
    assert linhas[0]["severidade"] == 4
    assert linhas[0]["tipo_evento"] == "EXCESSO_VELOCIDADE"


def test_sem_dados_em_raw_view_fica_vazia(apply_views, fetch_all):
    linhas = fetch_all("SELECT * FROM staging.eventos")
    assert linhas == []