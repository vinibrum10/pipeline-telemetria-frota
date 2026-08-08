"""
Carga no schema raw.

Decisão de arquitetura: cada tabela raw guarda só a chave natural do registro
(id, event_id, matricula) e o payload inteiro em uma coluna JSONB — nada de
colunas tipadas para cada campo aqui. Isso é proposital, não preguiça: a regra
de ouro do raw é ser cópia fiel do que a fonte devolveu, sem tratamento. Se eu
criar colunas tipadas já no raw, decisões de tipagem (essa data é texto ou
timestamp? esse número é inteiro ou pode vir nulo?) migram silenciosamente
para a extração, exatamente a camada errada para tomá-las. Tipagem e limpeza
são trabalho da camada staging — é o próximo passo do pipeline.

Carga é feita via upsert pela chave natural: rodar o script de novo atualiza
o registro existente em vez de duplicar. O raw aqui representa o estado mais
recente conhecido da fonte, não um histórico de todas as versões — para este
projeto isso é suficiente; manter histórico completo seria uma decisão
diferente (ex: guardar loaded_at como parte da chave).
"""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

_DDL = {
    "motoristas": """
        CREATE TABLE IF NOT EXISTS raw.motoristas (
            id TEXT PRIMARY KEY,
            payload JSONB NOT NULL,
            loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """,
    "eventos": """
        CREATE TABLE IF NOT EXISTS raw.eventos (
            event_id TEXT PRIMARY KEY,
            payload JSONB NOT NULL,
            loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """,
    "de_para_regional": """
        CREATE TABLE IF NOT EXISTS raw.de_para_regional (
            matricula TEXT PRIMARY KEY,
            payload JSONB NOT NULL,
            loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """,
}

_UPSERT = {
    "motoristas": """
        INSERT INTO raw.motoristas (id, payload)
        VALUES (:chave, :payload)
        ON CONFLICT (id) DO UPDATE
            SET payload = EXCLUDED.payload, loaded_at = now()
    """,
    "eventos": """
        INSERT INTO raw.eventos (event_id, payload)
        VALUES (:chave, :payload)
        ON CONFLICT (event_id) DO UPDATE
            SET payload = EXCLUDED.payload, loaded_at = now()
    """,
    "de_para_regional": """
        INSERT INTO raw.de_para_regional (matricula, payload)
        VALUES (:chave, :payload)
        ON CONFLICT (matricula) DO UPDATE
            SET payload = EXCLUDED.payload, loaded_at = now()
    """,
}


def get_engine() -> Engine:
    """
    Monta a conexão a partir do .env. Assume que o script roda na sua máquina
    (fora do container), por isso o host padrão é localhost, usando a porta
    que o docker-compose expõe — não o nome do serviço 'postgres', que só
    funciona de dentro da rede Docker.
    """
    load_dotenv()
    usuario = os.environ["POSTGRES_USER"]
    senha = os.environ["POSTGRES_PASSWORD"]
    banco = os.environ["POSTGRES_DB"]
    porta = os.environ.get("POSTGRES_PORT", "5432")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    url = f"postgresql+psycopg2://{usuario}:{senha}@{host}:{porta}/{banco}"
    return create_engine(url)


def _carregar(engine: Engine, tabela: str, campo_chave: str, registros: list[dict]) -> int:
    with engine.begin() as conn:
        conn.execute(text(_DDL[tabela]))
        for registro in registros:
            conn.execute(
                text(_UPSERT[tabela]),
                {"chave": registro[campo_chave], "payload": json.dumps(registro, ensure_ascii=False)},
            )
    return len(registros)


def load_motoristas(engine: Engine, motoristas: list[dict]) -> int:
    return _carregar(engine, "motoristas", "id", motoristas)


def load_eventos(engine: Engine, eventos: list[dict]) -> int:
    return _carregar(engine, "eventos", "event_id", eventos)


def load_de_para_regional(engine: Engine, linhas: list[dict]) -> int:
    return _carregar(engine, "de_para_regional", "matricula", linhas)