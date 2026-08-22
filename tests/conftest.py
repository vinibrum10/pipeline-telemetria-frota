"""
Fixtures compartilhadas para os testes das views de staging (src/transform/*.sql).

Estas views só existem de fato dentro de um Postgres (elas usam operadores JSONB,
window functions e casts específicos do Postgres), então os testes aqui são de
integração: sobem um schema `raw` isolado, aplicam os arquivos .sql reais do
projeto e conferem o resultado das views em `staging`.

Se não houver um Postgres acessível (ex: containers do docker-compose não estão
no ar), os testes são pulados via `pytest.skip` em vez de falhar o suite inteiro -
isso evita que a ausência de infraestrutura local seja confundida com um bug no
código.

Detalhe importante sobre as tabelas raw usadas nos testes: em produção
(src/load/raw_loader.py) elas têm chave primária na coluna natural (id /
event_id / matricula), então nunca existe mais de uma linha por chave - o upsert
sempre atualiza a linha existente. As views, porém, foram escritas para lidar
com duplicatas via `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY loaded_at DESC)`.
Para exercitar essa lógica de verdade, as tabelas raw criadas aqui NÃO têm
primary key (propositalmente), permitindo inserir múltiplas linhas com a mesma
chave natural e loaded_at diferentes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
TRANSFORM_DIR = ROOT / "src" / "transform"

# Colunas de chave natural de cada tabela raw, espelhando src/load/raw_loader.py.
RAW_TABLES: dict[str, str] = {
    "de_para_regional": "matricula",
    "motoristas": "id",
    "eventos": "event_id",
}


def _test_db_name() -> str:
    # NUNCA usar POSTGRES_DB aqui: esse é o banco operacional (o que
    # src/main.py carrega). Os testes de integração têm um banco próprio,
    # isolado, para poder truncar tabelas livremente sem risco de apagar
    # dado real - ver histórico: rodar contra POSTGRES_DB causou
    # UniqueViolation nos testes de dedup (tabelas raw já existiam com PK)
    # e truncou o schema raw do banco operacional.
    return os.environ.get("POSTGRES_TEST_DB", "elo_test")


def _build_url() -> str:
    usuario = os.environ.get("POSTGRES_USER", "elo_user")
    senha = os.environ.get("POSTGRES_PASSWORD", "troque_esta_senha")
    porta = os.environ.get("POSTGRES_PORT", "5432")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    return f"postgresql+psycopg2://{usuario}:{senha}@{host}:{porta}/{_test_db_name()}"


def _build_maintenance_url() -> str:
    """URL para o banco de manutenção `postgres`, usado só para criar o banco de teste."""
    usuario = os.environ.get("POSTGRES_USER", "elo_user")
    senha = os.environ.get("POSTGRES_PASSWORD", "troque_esta_senha")
    porta = os.environ.get("POSTGRES_PORT", "5432")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    return f"postgresql+psycopg2://{usuario}:{senha}@{host}:{porta}/postgres"


def _ensure_test_database_exists() -> None:
    """
    Cria o banco de teste (POSTGRES_TEST_DB) se ele ainda não existir.
    Conecta ao banco de manutenção `postgres` do mesmo servidor com
    autocommit, porque CREATE DATABASE não pode rodar dentro de uma
    transação.
    """
    nome = _test_db_name()
    eng = create_engine(_build_maintenance_url(), isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as conn:
            existe = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :nome"), {"nome": nome}
            ).scalar()
            if not existe:
                # `nome` vem de variável de ambiente controlada pelo próprio
                # projeto (.env / .env.example), não de input externo.
                conn.execute(text(f'CREATE DATABASE "{nome}"'))
    finally:
        eng.dispose()


def _assert_e_banco_de_teste(conn) -> None:
    """
    Trava de segurança independente da configuração: mesmo que
    POSTGRES_TEST_DB esteja mal configurado e aponte sem querer para o
    banco operacional, os testes recusam continuar em vez de rodar
    CREATE SCHEMA/TRUNCATE nele. Exige que o banco realmente conectado
    termine em "_test".
    """
    nome_banco = conn.execute(text("SELECT current_database()")).scalar()
    if not nome_banco.endswith("_test"):
        raise RuntimeError(
            f"Recusando rodar os testes de integração no banco '{nome_banco}': "
            "o nome não termina em '_test'. Essa trava existe para nunca truncar "
            "acidentalmente o banco operacional. Configure POSTGRES_TEST_DB no "
            "seu .env com um nome terminado em '_test' (ex.: elo_test)."
        )


@pytest.fixture(scope="session")
def engine() -> Engine:
    """
    Engine apontando para o banco de TESTE (POSTGRES_TEST_DB), nunca para o
    banco operacional (POSTGRES_DB). Cria o banco de teste se ele ainda não
    existir e recusa continuar se a conexão resolvida não apontar
    claramente para um banco de teste. Pula o suite se o Postgres não
    responder.
    """
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        pytest.skip("psycopg2 não instalado - pulando testes de integração com Postgres")

    _ensure_test_database_exists()

    eng = create_engine(_build_url())
    with eng.connect() as conn:  # se o Postgres não estiver acessível, falha aqui — não esconde com skip
        _assert_e_banco_de_teste(conn)
    return eng


@pytest.fixture(scope="session", autouse=True)
def _schemas(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS staging"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS marts"))


def _raw_ddl(tabela: str, chave: str) -> str:
    # Sem PRIMARY KEY de propósito: veja docstring do módulo.
    return f"""
        CREATE TABLE IF NOT EXISTS raw.{tabela} (
            {chave} TEXT,
            payload JSONB NOT NULL,
            loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """


@pytest.fixture
def raw_tables(engine: Engine):
    """Garante as tabelas raw.* (sem PK) vazias antes de cada teste."""
    with engine.begin() as conn:
        for tabela, chave in RAW_TABLES.items():
            conn.execute(text(_raw_ddl(tabela, chave)))
            conn.execute(text(f"TRUNCATE raw.{tabela}"))
    yield
    with engine.begin() as conn:
        for tabela in RAW_TABLES:
            conn.execute(text(f"TRUNCATE raw.{tabela}"))


@pytest.fixture
def apply_views(engine: Engine, raw_tables) -> None:
    """Aplica os arquivos .sql reais de src/transform/, em ordem, criando as views de staging."""
    arquivos = sorted(TRANSFORM_DIR.glob("*.sql"))
    assert arquivos, f"Nenhum arquivo .sql encontrado em {TRANSFORM_DIR}"
    with engine.begin() as conn:
        for caminho in arquivos:
            conn.execute(text(caminho.read_text(encoding="utf-8")))


@pytest.fixture
def insert_raw(engine: Engine):
    """
    Devolve uma função `insert_raw(tabela, registros, loaded_at=None)` que insere
    payloads brutos em raw.<tabela>. `registros` é uma lista de dicts (o payload
    JSON completo); a coluna de chave natural é extraída automaticamente. Se
    `loaded_at` for informado, todas as linhas inseridas nesta chamada recebem
    esse timestamp - útil para simular cargas em momentos diferentes e testar
    deduplicação.
    """

    def _insert(tabela: str, registros: list[dict], loaded_at: "str | None" = None) -> None:
        chave_col = RAW_TABLES[tabela]
        with engine.begin() as conn:
            for registro in registros:
                params = {
                    "chave": registro[chave_col],
                    "payload": json.dumps(registro, ensure_ascii=False),
                }
                if loaded_at is not None:
                    params["loaded_at"] = loaded_at
                    conn.execute(
                        text(
                            f"INSERT INTO raw.{tabela} ({chave_col}, payload, loaded_at) "
                            f"VALUES (:chave, :payload, :loaded_at)"
                        ),
                        params,
                    )
                else:
                    conn.execute(
                        text(f"INSERT INTO raw.{tabela} ({chave_col}, payload) VALUES (:chave, :payload)"),
                        params,
                    )

    return _insert


@pytest.fixture
def fetch_all(engine: Engine):
    """Devolve uma função `fetch_all(query, **params) -> list[dict]` para consultas SELECT."""

    def _fetch(query: str, **params) -> list[dict]:
        with engine.begin() as conn:
            rows = conn.execute(text(query), params).mappings().all()
            return [dict(row) for row in rows]

    return _fetch