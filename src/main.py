"""
Orquestra a extração e a carga da fonte de frota para o schema raw.

Uso (a partir da raiz do projeto, com o venv ativado e os containers no ar):
    python -m src.main
"""

from __future__ import annotations

from src.extract.fleet_source import read_de_para_regional, read_eventos, read_motoristas
from src.load.raw_loader import get_engine, load_de_para_regional, load_eventos, load_motoristas


def main() -> None:
    print("Lendo fontes locais (data/seed/)...")
    motoristas = read_motoristas()
    eventos = read_eventos()
    de_para = read_de_para_regional()

    print(f"  motoristas.json        {len(motoristas):>6} registros")
    print(f"  eventos.json           {len(eventos):>6} registros")
    print(f"  de_para_regional.csv   {len(de_para):>6} linhas")

    print("\nConectando ao Postgres...")
    engine = get_engine()

    print("Carregando raw.motoristas...")
    n_motoristas = load_motoristas(engine, motoristas)

    print("Carregando raw.eventos...")
    n_eventos = load_eventos(engine, eventos)

    print("Carregando raw.de_para_regional...")
    n_de_para = load_de_para_regional(engine, de_para)

    print(
        f"\nConcluído: {n_motoristas} motoristas, {n_eventos} eventos, "
        f"{n_de_para} linhas de regional carregados no schema raw."
    )


if __name__ == "__main__":
    main()