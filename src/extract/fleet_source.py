"""
Leitura da fonte de dados da frota.

Hoje a "fonte" é local: os arquivos gerados por scripts/gerar_dados_fake.py em
data/seed/. Quando este pipeline conectar na API de telemetria de verdade, só
este módulo muda — cada função passa a fazer uma chamada HTTP em vez de ler um
arquivo, mas continua devolvendo a mesma estrutura de dados. O resto do
pipeline (load, transform) não precisa saber a diferença.

Este módulo não sabe nada sobre banco de dados. Só lê e devolve.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

DEFAULT_SEED_DIR = Path("data/seed")


def read_motoristas(seed_dir: Path = DEFAULT_SEED_DIR) -> list[dict]:
    """Lê o cadastro de motoristas (formato da API de telemetria)."""
    caminho = seed_dir / "motoristas.json"
    with caminho.open(encoding="utf-8") as f:
        return json.load(f)


def read_eventos(seed_dir: Path = DEFAULT_SEED_DIR) -> list[dict]:
    """Lê os eventos de telemetria / infrações."""
    caminho = seed_dir / "eventos.json"
    with caminho.open(encoding="utf-8") as f:
        return json.load(f)


def read_de_para_regional(seed_dir: Path = DEFAULT_SEED_DIR) -> list[dict]:
    """Lê a planilha de-para: matrícula -> regional."""
    caminho = seed_dir / "de_para_regional.csv"
    with caminho.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))