from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.extract.fleet_source import read_de_para_regional, read_eventos, read_motoristas
from src.load.raw_loader import get_engine, load_de_para_regional, load_eventos, load_motoristas

LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "execucoes.jsonl"


def _registrar_execucao(
    inicio: datetime,
    status: str,
    contagens: dict,
    etapa_falha: "str | None",
    erro: "str | None",
) -> None:
    """Grava uma linha JSON em logs/execucoes.jsonl com o resultado da execução."""
    fim = datetime.now(timezone.utc)
    registro = {
        "execucao_id": str(uuid.uuid4()),
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        "duracao_segundos": round((fim - inicio).total_seconds(), 3),
        "status": status,
        "etapa_falha": etapa_falha,
        "motoristas_processados": contagens.get("motoristas"),
        "eventos_processados": contagens.get("eventos"),
        "de_para_processados": contagens.get("de_para_regional"),
        "erro": erro,
    }
    LOG_PATH.parent.mkdir(exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def main() -> None:
    """Orquestra extract -> load das três fontes para o schema raw, registrando a execução."""
    inicio = datetime.now(timezone.utc)
    contagens: dict[str, int] = {}
    etapa_atual = "leitura_fontes"

    try:
        print("Lendo fontes locais (data/seed/)...")
        motoristas = read_motoristas()
        eventos = read_eventos()
        de_para = read_de_para_regional()

        print(f"  motoristas.json        {len(motoristas):>6} registros")
        print(f"  eventos.json           {len(eventos):>6} registros")
        print(f"  de_para_regional.csv   {len(de_para):>6} linhas")

        etapa_atual = "conexao"
        print("\nConectando ao Postgres...")
        engine = get_engine()

        etapa_atual = "carga_motoristas"
        print("Carregando raw.motoristas...")
        contagens["motoristas"] = load_motoristas(engine, motoristas)

        etapa_atual = "carga_eventos"
        print("Carregando raw.eventos...")
        contagens["eventos"] = load_eventos(engine, eventos)

        etapa_atual = "carga_regionais"
        print("Carregando raw.de_para_regional...")
        contagens["de_para_regional"] = load_de_para_regional(engine, de_para)

        print(
            f"\nConcluído: {contagens['motoristas']} motoristas, {contagens['eventos']} eventos, "
            f"{contagens['de_para_regional']} linhas de regional processadas no schema raw."
        )

        try:
            _registrar_execucao(inicio, status="sucesso", contagens=contagens, etapa_falha=None, erro=None)
        except Exception as log_exc:
            print(f"[AVISO] Falha ao registrar log de execução: {log_exc}", file=sys.stderr)

    except Exception as exc:
        try:
            _registrar_execucao(
                inicio, status="falha", contagens=contagens, etapa_falha=etapa_atual, erro=str(exc)
            )
        except Exception as log_exc:
            print(f"[AVISO] Falha ao registrar log de execução: {log_exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()