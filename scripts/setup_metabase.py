"""
scripts/setup_metabase.py

Automatiza a configuração do Metabase para o pipeline-telemetria-frota:
- completa o setup inicial do Metabase (usuário admin) se ainda não existir;
- valida e garante a conexão com o Postgres do projeto;
- recria as 4 perguntas do dashboard "Segurança Operacional — Frota" via SQL nativo;
- recria o próprio dashboard, vinculando as 4 perguntas.

Idempotente: pode ser rodado várias vezes sem duplicar objetos.

Requer (ver .env.example):
    METABASE_URL            (default: http://localhost:3000)
    METABASE_ADMIN_EMAIL
    METABASE_ADMIN_PASSWORD
    METABASE_DB_HOST        (host do Postgres do PONTO DE VISTA DO CONTAINER
                              do Metabase na rede Docker; default: postgres)
    POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

from __future__ import annotations

import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

METABASE_URL = os.environ.get("METABASE_URL", "http://localhost:3000").rstrip("/")
ADMIN_EMAIL = os.environ["METABASE_ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["METABASE_ADMIN_PASSWORD"]

# Host do Postgres como visto PELO CONTAINER do Metabase na rede Docker -
# nunca "localhost", mesmo que o script rode fora do Docker.
POSTGRES_HOST_DOCKER = os.environ.get("METABASE_DB_HOST", "postgres")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.environ["POSTGRES_DB"]
POSTGRES_USER = os.environ["POSTGRES_USER"]
POSTGRES_PASSWORD = os.environ["POSTGRES_PASSWORD"]

DATABASE_NAME = "Pipeline Telemetria Frota"

QUESTIONS = [
    {
        "name": "Eventos por Regional — Visão Geral",
        "sql": """
            SELECT
                "marts"."eventos_por_regional"."regional" AS "regional",
                SUM("marts"."eventos_por_regional"."total_eventos") AS "sum"
            FROM "marts"."eventos_por_regional"
            GROUP BY "marts"."eventos_por_regional"."regional"
            ORDER BY "marts"."eventos_por_regional"."regional" ASC
        """.strip(),
        "display": "bar",
    },
    {
        "name": "Eventos por Regional — por Tipo de Evento",
        "sql": """
            SELECT
                "marts"."eventos_por_regional"."regional" AS "regional",
                "marts"."eventos_por_regional"."tipo_evento" AS "tipo_evento",
                SUM("marts"."eventos_por_regional"."total_eventos") AS "sum"
            FROM "marts"."eventos_por_regional"
            GROUP BY
                "marts"."eventos_por_regional"."regional",
                "marts"."eventos_por_regional"."tipo_evento"
            ORDER BY
                "marts"."eventos_por_regional"."regional" ASC,
                "marts"."eventos_por_regional"."tipo_evento" ASC
        """.strip(),
        "display": "bar",
    },
    {
        "name": "Motoristas por Total de Eventos",
        "sql": """
            SELECT
                "marts"."infracoes_por_motorista"."nome" AS "nome",
                SUM("marts"."infracoes_por_motorista"."total_eventos") AS "sum"
            FROM "marts"."infracoes_por_motorista"
            GROUP BY "marts"."infracoes_por_motorista"."nome"
            ORDER BY "sum" DESC, "marts"."infracoes_por_motorista"."nome" ASC
            LIMIT 10
        """.strip(),
        "display": "bar",
    },
    {
        "name": "Tendência Diária de Infrações (Mai-Ago)",
        "sql": """
            SELECT
                "marts"."infracoes_por_periodo"."data_referencia" AS "data_referencia",
                SUM("marts"."infracoes_por_periodo"."total_eventos") AS "sum"
            FROM "marts"."infracoes_por_periodo"
            GROUP BY "marts"."infracoes_por_periodo"."data_referencia"
            ORDER BY "marts"."infracoes_por_periodo"."data_referencia" ASC
        """.strip(),
        "display": "line",
    },
]

DASHBOARD_NAME = "Segurança Operacional — Frota"
DASHBOARD_DESCRIPTION = (
    "Painel de segurança operacional da frota: volume de eventos por regional, "
    "ranking de motoristas e tendência temporal."
)


def wait_for_metabase(timeout_seconds: int = 120) -> None:
    """Aguarda o Metabase responder no endpoint de health check."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            resp = requests.get(f"{METABASE_URL}/api/health", timeout=5)
            if resp.status_code == 200:
                return
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    raise RuntimeError(f"Metabase não respondeu em {METABASE_URL} após {timeout_seconds}s")


def get_session_token() -> str:
    """
    Se o Metabase ainda não tiver sido configurado (instância nova), completa
    o setup inicial via /api/setup, criando o admin e a conexão com o Postgres
    na mesma chamada. Caso já exista um admin, apenas faz login.
    """
    props = requests.get(f"{METABASE_URL}/api/session/properties", timeout=10).json()
    if not props.get("has-user-setup", True):
        resp = requests.post(
            f"{METABASE_URL}/api/setup",
            json={
                "token": props["setup-token"],
                "user": {
                    "first_name": "Admin",
                    "last_name": "Pipeline",
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD,
                },
                "prefs": {"site_name": "Pipeline Telemetria Frota", "allow_tracking": False},
                "database": {
                    "engine": "postgres",
                    "name": DATABASE_NAME,
                    "details": {
                        "host": POSTGRES_HOST_DOCKER,
                        "port": POSTGRES_PORT,
                        "dbname": POSTGRES_DB,
                        "user": POSTGRES_USER,
                        "password": POSTGRES_PASSWORD,
                    },
                },
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    resp = requests.post(
        f"{METABASE_URL}/api/session",
        json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def validate_database_connection(session: requests.Session) -> None:
    """Valida as credenciais/host do Postgres via endpoint oficial, antes de criar a conexão."""
    resp = session.post(
        f"{METABASE_URL}/api/database/validate",
        json={
            "details": {
                "engine": "postgres",
                "details": {
                    "host": POSTGRES_HOST_DOCKER,
                    "port": POSTGRES_PORT,
                    "dbname": POSTGRES_DB,
                    "user": POSTGRES_USER,
                    "password": POSTGRES_PASSWORD,
                },
            }
        },
        timeout=30,
    )
    resp.raise_for_status()
    errors = resp.json().get("errors") or {}
    if errors:
        raise RuntimeError(f"Conexão com o Postgres inválida: {errors}")


def ensure_database(session: requests.Session) -> int:
    """Garante que existe uma conexão com o Postgres do projeto; retorna seu id."""
    res = session.get(f"{METABASE_URL}/api/database", timeout=10).json()
    databases = res.get("data", res) if isinstance(res, dict) else res
    for db in databases:
        if db["name"] == DATABASE_NAME:
            return db["id"]

    validate_database_connection(session)

    resp = session.post(
        f"{METABASE_URL}/api/database",
        json={
            "engine": "postgres",
            "name": DATABASE_NAME,
            "details": {
                "host": POSTGRES_HOST_DOCKER,
                "port": POSTGRES_PORT,
                "dbname": POSTGRES_DB,
                "user": POSTGRES_USER,
                "password": POSTGRES_PASSWORD,
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def ensure_question(session: requests.Session, database_id: int, question: dict) -> int:
    """Cria a pergunta se ainda não existir (por nome); retorna o id da pergunta."""
    existing = session.get(f"{METABASE_URL}/api/card", timeout=10).json()
    for card in existing:
        if card["name"] == question["name"]:
            return card["id"]

    resp = session.post(
        f"{METABASE_URL}/api/card",
        json={
            "name": question["name"],
            "dataset_query": {
                "type": "native",
                "native": {"query": question["sql"]},
                "database": database_id,
            },
            "display": question["display"],
            "visualization_settings": {},
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def ensure_dashboard(session: requests.Session, card_ids: list[int]) -> int:
    """Cria o dashboard se ainda não existir e vincula as perguntas a ele."""
    existing = session.get(f"{METABASE_URL}/api/dashboard", timeout=10).json()
    dashboard_id = None
    for dash in existing:
        if dash["name"] == DASHBOARD_NAME:
            dashboard_id = dash["id"]
            break

    if dashboard_id is None:
        resp = session.post(
            f"{METABASE_URL}/api/dashboard",
            json={"name": DASHBOARD_NAME, "description": DASHBOARD_DESCRIPTION},
            timeout=30,
        )
        resp.raise_for_status()
        dashboard_id = resp.json()["id"]

    dashcards = [
        {
            "id": -(i + 1),
            "card_id": card_id,
            "row": (i // 2) * 4,
            "col": (i % 2) * 12,
            "size_x": 12,
            "size_y": 4,
        }
        for i, card_id in enumerate(card_ids)
    ]
    resp = session.put(
        f"{METABASE_URL}/api/dashboard/{dashboard_id}",
        json={"dashcards": dashcards},
        timeout=30,
    )
    resp.raise_for_status()
    return dashboard_id


def main() -> None:
    wait_for_metabase()
    token = get_session_token()

    session = requests.Session()
    session.headers.update({"X-Metabase-Session": token})

    database_id = ensure_database(session)
    card_ids = [ensure_question(session, database_id, q) for q in QUESTIONS]
    dashboard_id = ensure_dashboard(session, card_ids)

    print(f"Dashboard pronto: {METABASE_URL}/dashboard/{dashboard_id}")


if __name__ == "__main__":
    main()