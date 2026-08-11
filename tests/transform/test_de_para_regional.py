"""
Testes para a view staging.de_para_regional (src/transform/001_staging_de_para_regional.sql).

Cobre:
- deduplicação por matricula, mantendo o payload de loaded_at mais recente;
- normalização de regional vazio/whitespace para NULL (NULLIF + trim);
- normalização de email (trim + lower);
- passagem direta de centro_custo (sem tratamento);
- ausência de linha quando raw está vazio.
"""

from __future__ import annotations


def _linha(**overrides) -> dict:
    base = {
        "matricula": "MAT0001",
        "nome": "Fulano da Silva",
        "regional": "Sudeste",
        "centro_custo": "CC-100",
        "email": "fulano@example.com",
    }
    base.update(overrides)
    return base


def test_view_expoe_colunas_esperadas(apply_views, insert_raw, fetch_all):
    insert_raw("de_para_regional", [_linha()])

    linhas = fetch_all("SELECT * FROM staging.de_para_regional WHERE matricula = 'MAT0001'")
    assert len(linhas) == 1
    assert set(linhas[0].keys()) == {"matricula", "regional", "centro_custo", "email"}


def test_email_e_normalizado_para_minusculo_e_sem_espacos(apply_views, insert_raw, fetch_all):
    insert_raw(
        "de_para_regional",
        [_linha(matricula="MAT0002", email="  Fulano.Silva@EXAMPLE.com  ")],
    )

    linhas = fetch_all("SELECT email FROM staging.de_para_regional WHERE matricula = 'MAT0002'")
    assert linhas[0]["email"] == "fulano.silva@example.com"


def test_regional_vazio_ou_so_espacos_vira_null(apply_views, insert_raw, fetch_all):
    insert_raw(
        "de_para_regional",
        [
            _linha(matricula="MAT0003", regional=""),
            _linha(matricula="MAT0004", regional="   "),
        ],
    )

    linhas = fetch_all(
        "SELECT matricula, regional FROM staging.de_para_regional "
        "WHERE matricula IN ('MAT0003', 'MAT0004') ORDER BY matricula",
    )
    assert linhas[0]["regional"] is None
    assert linhas[1]["regional"] is None


def test_regional_preenchido_e_preservado(apply_views, insert_raw, fetch_all):
    insert_raw("de_para_regional", [_linha(matricula="MAT0005", regional="Nordeste")])

    linhas = fetch_all("SELECT regional FROM staging.de_para_regional WHERE matricula = 'MAT0005'")
    assert linhas[0]["regional"] == "Nordeste"


def test_centro_custo_passa_sem_tratamento(apply_views, insert_raw, fetch_all):
    insert_raw("de_para_regional", [_linha(matricula="MAT0006", centro_custo="  CC-999  ")])

    linhas = fetch_all("SELECT centro_custo FROM staging.de_para_regional WHERE matricula = 'MAT0006'")
    # centro_custo não passa por trim na view - deve vir exatamente como no payload.
    assert linhas[0]["centro_custo"] == "  CC-999  "


def test_deduplica_por_matricula_mantendo_loaded_at_mais_recente(apply_views, insert_raw, fetch_all):
    insert_raw(
        "de_para_regional",
        [_linha(matricula="MAT0007", regional="Antiga", email="antigo@example.com")],
        loaded_at="2024-01-01T00:00:00Z",
    )
    insert_raw(
        "de_para_regional",
        [_linha(matricula="MAT0007", regional="Nova", email="novo@example.com")],
        loaded_at="2024-06-01T00:00:00Z",
    )

    linhas = fetch_all("SELECT regional, email FROM staging.de_para_regional WHERE matricula = 'MAT0007'")
    assert len(linhas) == 1
    assert linhas[0]["regional"] == "Nova"
    assert linhas[0]["email"] == "novo@example.com"


def test_deduplica_ignorando_ordem_de_insercao(apply_views, insert_raw, fetch_all):
    """A linha mais recente deve prevalecer mesmo se for inserida primeiro."""
    insert_raw(
        "de_para_regional",
        [_linha(matricula="MAT0009", regional="Nova", email="novo@example.com")],
        loaded_at="2024-06-01T00:00:00Z",
    )
    insert_raw(
        "de_para_regional",
        [_linha(matricula="MAT0009", regional="Antiga", email="antigo@example.com")],
        loaded_at="2024-01-01T00:00:00Z",
    )

    linhas = fetch_all("SELECT regional FROM staging.de_para_regional WHERE matricula = 'MAT0009'")
    assert len(linhas) == 1
    assert linhas[0]["regional"] == "Nova"


def test_email_ausente_no_payload_resulta_em_null(apply_views, insert_raw, fetch_all):
    linha = _linha(matricula="MAT0008")
    del linha["email"]
    insert_raw("de_para_regional", [linha])

    linhas = fetch_all("SELECT email FROM staging.de_para_regional WHERE matricula = 'MAT0008'")
    assert linhas[0]["email"] is None


def test_sem_dados_em_raw_view_fica_vazia(apply_views, fetch_all):
    linhas = fetch_all("SELECT * FROM staging.de_para_regional")
    assert linhas == []