"""
Testes para .env.example.

O arquivo é o template copiado pelo usuário para .env (README.md e o próprio
comentário no topo do arquivo instruem isso), e é lido por
src/load/raw_loader.get_engine() via python-dotenv. Esses testes garantem que:

- todas as variáveis que get_engine() espera estão presentes e com um valor
  (não vazias);
- POSTGRES_HOST=localhost está definido explicitamente (adicionado nesta PR -
  antes, get_engine() dependia só do fallback em código para "localhost");
- POSTGRES_PORT e METABASE_PORT são números de porta válidos;
- o arquivo não tem entradas vazias/malformadas (ex: uma linha em branco sendo
  interpretada como uma variável de nome vazio).
"""

from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values

ENV_EXAMPLE_PATH = Path(__file__).resolve().parents[1] / ".env.example"

REQUIRED_KEYS = {
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_PORT",
    "POSTGRES_HOST",
    "METABASE_PORT",
}


def _load_values() -> dict[str, str | None]:
    return dotenv_values(ENV_EXAMPLE_PATH)


def test_arquivo_existe():
    assert ENV_EXAMPLE_PATH.is_file()


def test_contem_todas_as_chaves_esperadas():
    valores = _load_values()
    assert REQUIRED_KEYS <= set(valores.keys())


def test_nenhuma_chave_obrigatoria_esta_vazia():
    valores = _load_values()
    for chave in REQUIRED_KEYS:
        assert valores.get(chave), f"{chave} não deveria estar vazia em .env.example"


def test_nao_ha_chave_vazia_no_arquivo():
    """
    Regression: antes desta PR havia uma linha em branco entre POSTGRES_PORT e
    METABASE_PORT. dotenv_values ignora linhas em branco (não gera chave ''),
    então este teste confirma que nenhuma variável com nome vazio ou malformada
    foi introduzida.
    """
    valores = _load_values()
    assert "" not in valores
    assert None not in valores


def test_postgres_host_definido_como_localhost():
    """POSTGRES_HOST=localhost foi adicionado nesta PR (antes o campo não existia)."""
    valores = _load_values()
    assert valores["POSTGRES_HOST"] == "localhost"


def test_postgres_port_e_numerico():
    valores = _load_values()
    assert valores["POSTGRES_PORT"].isdigit()
    assert 0 < int(valores["POSTGRES_PORT"]) <= 65535


def test_metabase_port_e_numerico():
    valores = _load_values()
    assert valores["METABASE_PORT"].isdigit()
    assert 0 < int(valores["METABASE_PORT"]) <= 65535


def test_postgres_port_corresponde_ao_padrao_do_docker_compose():
    """Consistência com o healthcheck/porta padrão descrita no docker-compose.yml."""
    valores = _load_values()
    assert valores["POSTGRES_PORT"] == "5432"


def test_postgres_password_nao_deve_ser_usada_em_producao():
    """Sanidade: o valor de exemplo é claramente um placeholder, não uma senha real."""
    valores = _load_values()
    assert valores["POSTGRES_PASSWORD"] == "troque_esta_senha"