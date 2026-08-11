"""
Testes para a view staging.motoristas (src/transform/002_staging_motoristas.sql).

Cobre:
- extração de campos simples e aninhados (license.category / license.expiration_date);
- normalização de espaços múltiplos no nome;
- cast de active para boolean e expiration_date para date;
- LEFT JOIN com staging.de_para_regional por matricula (registry_id);
- ausência de correspondência no de-para não deve eliminar o motorista (LEFT JOIN);
- deduplicação por id, mantendo o payload de loaded_at mais recente;
- ausência do bloco `license` não deve quebrar a view.

Depende de staging.de_para_regional (001) já estar aplicada - isso é feito pela
fixture `apply_views`, que roda todos os arquivos de src/transform/ em ordem.
"""

from __future__ import annotations


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


def test_view_expoe_colunas_esperadas(apply_views, insert_raw, fetch_all):
    insert_raw("motoristas", [_motorista()])
    insert_raw("de_para_regional", [_de_para()])

    linhas = fetch_all("SELECT * FROM staging.motoristas WHERE motorista_id = :id", id=_motorista()["id"])
    assert len(linhas) == 1
    assert set(linhas[0].keys()) == {
        "motorista_id",
        "codigo_motorista",
        "matricula",
        "nome",
        "cpf",
        "ativo",
        "cnh_categoria",
        "cnh_validade",
        "regional",
        "centro_custo",
    }


def test_campos_simples_passam_direto(apply_views, insert_raw, fetch_all):
    insert_raw("motoristas", [_motorista(id="id-simples", cpf="98765432100", driver_code="DRV-0099")])

    linhas = fetch_all(
        "SELECT motorista_id, codigo_motorista, matricula, cpf FROM staging.motoristas WHERE motorista_id = 'id-simples'"
    )
    assert linhas[0]["motorista_id"] == "id-simples"
    assert linhas[0]["codigo_motorista"] == "DRV-0099"
    assert linhas[0]["matricula"] == "MAT0001"
    assert linhas[0]["cpf"] == "98765432100"


def test_nome_normaliza_espacos_multiplos(apply_views, insert_raw, fetch_all):
    insert_raw("motoristas", [_motorista(id="id-espacos", name="  João   da   Silva  ")])

    linhas = fetch_all("SELECT nome FROM staging.motoristas WHERE motorista_id = 'id-espacos'")
    assert linhas[0]["nome"] == "João da Silva"


def test_ativo_e_convertido_para_boolean(apply_views, insert_raw, fetch_all):
    insert_raw(
        "motoristas",
        [
            _motorista(id="id-ativo", active=True),
            _motorista(id="id-inativo", active=False, registry_id="MAT0002"),
        ],
    )

    linhas = fetch_all(
        "SELECT motorista_id, ativo FROM staging.motoristas WHERE motorista_id IN ('id-ativo', 'id-inativo') "
        "ORDER BY motorista_id"
    )
    por_id = {linha["motorista_id"]: linha["ativo"] for linha in linhas}
    assert por_id["id-ativo"] is True
    assert por_id["id-inativo"] is False


def test_license_categoria_e_validade_extraidas(apply_views, insert_raw, fetch_all):
    insert_raw(
        "motoristas",
        [_motorista(id="id-license", license={"number": "X", "category": "D", "expiration_date": "2027-12-31"})],
    )

    linhas = fetch_all("SELECT cnh_categoria, cnh_validade FROM staging.motoristas WHERE motorista_id = 'id-license'")
    assert linhas[0]["cnh_categoria"] == "D"
    assert str(linhas[0]["cnh_validade"]) == "2027-12-31"


def test_license_ausente_resulta_em_colunas_nulas(apply_views, insert_raw, fetch_all):
    motorista = _motorista(id="id-sem-license")
    del motorista["license"]
    insert_raw("motoristas", [motorista])

    linhas = fetch_all("SELECT cnh_categoria, cnh_validade FROM staging.motoristas WHERE motorista_id = 'id-sem-license'")
    assert linhas[0]["cnh_categoria"] is None
    assert linhas[0]["cnh_validade"] is None


def test_join_com_de_para_quando_matricula_corresponde(apply_views, insert_raw, fetch_all):
    insert_raw("motoristas", [_motorista(id="id-com-regional", registry_id="MAT0010")])
    insert_raw("de_para_regional", [_de_para(matricula="MAT0010", regional="Norte", centro_custo="CC-777")])

    linhas = fetch_all("SELECT regional, centro_custo FROM staging.motoristas WHERE motorista_id = 'id-com-regional'")
    assert linhas[0]["regional"] == "Norte"
    assert linhas[0]["centro_custo"] == "CC-777"


def test_join_retorna_null_quando_matricula_nao_tem_correspondencia(apply_views, insert_raw, fetch_all):
    insert_raw("motoristas", [_motorista(id="id-sem-regional", registry_id="MAT-INEXISTENTE")])
    # Nenhum registro em de_para_regional para MAT-INEXISTENTE - o motorista não deve
    # ser descartado (LEFT JOIN), apenas regional/centro_custo ficam NULL.

    linhas = fetch_all(
        "SELECT motorista_id, regional, centro_custo FROM staging.motoristas WHERE motorista_id = 'id-sem-regional'"
    )
    assert len(linhas) == 1
    assert linhas[0]["regional"] is None
    assert linhas[0]["centro_custo"] is None


def test_deduplica_por_id_mantendo_loaded_at_mais_recente(apply_views, insert_raw, fetch_all):
    insert_raw(
        "motoristas",
        [_motorista(id="id-dup", name="Nome Antigo", active=True)],
        loaded_at="2024-01-01T00:00:00Z",
    )
    insert_raw(
        "motoristas",
        [_motorista(id="id-dup", name="Nome Novo", active=False)],
        loaded_at="2024-06-01T00:00:00Z",
    )

    linhas = fetch_all("SELECT nome, ativo FROM staging.motoristas WHERE motorista_id = 'id-dup'")
    assert len(linhas) == 1
    assert linhas[0]["nome"] == "Nome Novo"
    assert linhas[0]["ativo"] is False


def test_sem_dados_em_raw_view_fica_vazia(apply_views, fetch_all):
    linhas = fetch_all("SELECT * FROM staging.motoristas")
    assert linhas == []