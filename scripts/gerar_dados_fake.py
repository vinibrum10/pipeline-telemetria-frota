"""
Gerador de dados sintéticos para o Projeto Elo (versão pública / portfólio).

Produz um conjunto de dados fictícios com a MESMA ESTRUTURA da API de
telemetria de frota usada no projeto real, permitindo que todo o pipeline
(ingestão -> PostgreSQL -> painéis) rode de ponta a ponta sem nenhum dado
pessoal ou corporativo real.

Saídas (em data/seed/):
    motoristas.json        - cadastro de motoristas (formato da API)
    eventos.json           - eventos de telemetria / infrações
    de_para_regional.csv   - mapeamento motorista -> regional (planilha)

Uso:
    python scripts/gerar_dados_fake.py
    python scripts/gerar_dados_fake.py --motoristas 414 --dias 90 --seed 42
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from faker import Faker

# ---------------------------------------------------------------------------
# Configuração de domínio
# ---------------------------------------------------------------------------

REGIONAIS = [
    "Regional Norte",
    "Regional Nordeste",
    "Regional Centro-Oeste",
    "Regional Sudeste",
    "Regional Sul",
]

# Tipos de evento com peso relativo (eventos leves são muito mais frequentes)
# e severidade, usada depois para ranquear motoristas nos painéis.
TIPOS_EVENTO = [
    {"codigo": "EXCESSO_VELOCIDADE", "descricao": "Excesso de velocidade", "peso": 30, "severidade": 3},
    {"codigo": "FRENAGEM_BRUSCA", "descricao": "Frenagem brusca", "peso": 25, "severidade": 2},
    {"codigo": "ACELERACAO_BRUSCA", "descricao": "Aceleração brusca", "peso": 20, "severidade": 2},
    {"codigo": "CURVA_AGRESSIVA", "descricao": "Curva agressiva", "peso": 12, "severidade": 2},
    {"codigo": "USO_CELULAR", "descricao": "Uso de celular ao volante", "peso": 6, "severidade": 5},
    {"codigo": "SEM_CINTO", "descricao": "Condução sem cinto de segurança", "peso": 5, "severidade": 4},
    {"codigo": "FADIGA", "descricao": "Indício de fadiga do condutor", "peso": 2, "severidade": 5},
]

CATEGORIAS_CNH = ["B", "C", "D", "E"]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def gerar_cpf_ficticio(rnd: random.Random) -> str:
    """
    Gera um CPF sintaticamente válido (dígitos verificadores corretos) mas
    fictício. Usado apenas para que o pipeline exercite validação/formatação
    de CPF sem jamais tocar em um documento real.
    """
    base = [rnd.randint(0, 9) for _ in range(9)]

    def digito(numeros: list[int]) -> int:
        peso = len(numeros) + 1
        soma = sum(n * (peso - i) for i, n in enumerate(numeros))
        resto = (soma * 10) % 11
        return 0 if resto == 10 else resto

    base.append(digito(base))
    base.append(digito(base))
    return "".join(map(str, base))


def slug_email(nome: str) -> str:
    """Converte 'João da Silva' -> 'joao.silva'."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    partes = [p for p in sem_acento.lower().split() if len(p) > 2]
    if len(partes) >= 2:
        return f"{partes[0]}.{partes[-1]}"
    return partes[0] if partes else "usuario"


def escolher_evento(rnd: random.Random) -> dict:
    pesos = [t["peso"] for t in TIPOS_EVENTO]
    return rnd.choices(TIPOS_EVENTO, weights=pesos, k=1)[0]


# ---------------------------------------------------------------------------
# Geradores
# ---------------------------------------------------------------------------

def gerar_motoristas(fake: Faker, rnd: random.Random, quantidade: int) -> list[dict]:
    """
    Espelha o formato retornado pelo endpoint de motoristas da API de
    telemetria: id, name, cpf, registry_id, phone_numbers, active,
    driver_code, license.

    Observação de domínio: no dado real o campo `groups` vem quase sempre
    vazio — por isso a regional NÃO é gerada aqui. Ela vem do de-para
    (planilha de cadastro), reproduzindo o mesmo desafio de integração.
    """
    motoristas = []
    for i in range(quantidade):
        nome = fake.name()
        ativo = rnd.random() > 0.08  # ~8% inativos, como numa base real
        motoristas.append(
            {
                "id": str(uuid.UUID(int=rnd.getrandbits(128), version=4)),
                "name": nome,
                "cpf": gerar_cpf_ficticio(rnd),
                "registry_id": f"MAT{100000 + i}",
                "phone_numbers": [fake.msisdn()[:11]],
                "active": ativo,
                "driver_code": f"DRV-{i + 1:04d}",
                "license": {
                    "number": str(rnd.randint(10**10, 10**11 - 1)),
                    "category": rnd.choice(CATEGORIAS_CNH),
                    "expiration_date": (
                        datetime.now(timezone.utc) + timedelta(days=rnd.randint(-180, 1800))
                    ).strftime("%Y-%m-%d"),
                },
                "groups": [],  # vazio de propósito: replica o dado real
            }
        )
    return motoristas


def gerar_eventos(
    rnd: random.Random,
    motoristas: list[dict],
    dias: int,
    eventos_por_dia: int,
) -> list[dict]:
    """
    Gera eventos de telemetria distribuídos ao longo do período.

    A distribuição é intencionalmente desbalanceada (lei de Pareto): uma
    minoria de motoristas concentra a maior parte das ocorrências. Isso é o
    que torna o painel de "quem mais comete infrações" interessante — com
    distribuição uniforme o ranking não teria sinal nenhum.
    """
    ativos = [m for m in motoristas if m["active"]]
    if not ativos:
        raise ValueError("Nenhum motorista ativo para gerar eventos.")

    # Peso de risco por motorista: a maioria é de baixo risco, poucos são
    # reincidentes contumazes.
    pesos_motorista = [rnd.paretovariate(1.6) for _ in ativos]

    inicio = datetime.now(timezone.utc) - timedelta(days=dias)
    eventos = []

    for dia in range(dias):
        data_base = inicio + timedelta(days=dia)
        # Menos eventos nos fins de semana (operação reduzida).
        fator = 0.35 if data_base.weekday() >= 5 else 1.0
        total_dia = max(0, int(rnd.gauss(eventos_por_dia * fator, eventos_por_dia * 0.2)))

        for _ in range(total_dia):
            motorista = rnd.choices(ativos, weights=pesos_motorista, k=1)[0]
            tipo = escolher_evento(rnd)
            momento = data_base + timedelta(
                hours=rnd.randint(5, 21),
                minutes=rnd.randint(0, 59),
                seconds=rnd.randint(0, 59),
            )
            velocidade = None
            if tipo["codigo"] == "EXCESSO_VELOCIDADE":
                velocidade = round(rnd.uniform(85, 135), 1)

            eventos.append(
                {
                    "event_id": str(uuid.UUID(int=rnd.getrandbits(128), version=4)),
                    "driver_id": motorista["id"],
                    "driver_code": motorista["driver_code"],
                    "vehicle_plate": f"{rnd.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"
                    f"{rnd.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"
                    f"{rnd.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"
                    f"{rnd.randint(0, 9)}{rnd.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"
                    f"{rnd.randint(0, 9)}{rnd.randint(0, 9)}",
                    "event_type": tipo["codigo"],
                    "event_description": tipo["descricao"],
                    "severity": tipo["severidade"],
                    "occurred_at": momento.isoformat(),
                    "speed_kmh": velocidade,
                    "latitude": round(rnd.uniform(-33.7, -5.0), 6),
                    "longitude": round(rnd.uniform(-53.0, -38.0), 6),
                }
            )

    eventos.sort(key=lambda e: e["occurred_at"])
    return eventos


def gerar_de_para_regional(rnd: random.Random, motoristas: list[dict]) -> list[dict]:
    """
    Reproduz a planilha de cadastro que resolve a lacuna da API: é ela que
    traz a regional de cada motorista. Inclui imperfeições propositais
    (matrículas ausentes) para que o pipeline precise tratar dado sujo,
    como acontece na prática.
    """
    linhas = []
    for m in motoristas:
        # ~3% das linhas sem regional preenchida: dado incompleto é a regra,
        # não a exceção, em planilha mantida à mão.
        regional = rnd.choice(REGIONAIS) if rnd.random() > 0.03 else ""
        linhas.append(
            {
                "matricula": m["registry_id"],
                "nome": m["name"],
                "regional": regional,
                "centro_custo": f"CC-{rnd.randint(1000, 9999)}",
                "email": f"{slug_email(m['name'])}@empresa-exemplo.com.br",
            }
        )
    return linhas


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------

def escrever_json(caminho: Path, dados: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def escrever_csv(caminho: Path, linhas: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        writer.writeheader()
        writer.writerows(linhas)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera dados sintéticos para o Projeto Elo (versão pública)."
    )
    parser.add_argument("--motoristas", type=int, default=414, help="Quantidade de motoristas")
    parser.add_argument("--dias", type=int, default=90, help="Período histórico em dias")
    parser.add_argument(
        "--eventos-por-dia", type=int, default=120, help="Média de eventos por dia útil"
    )
    parser.add_argument("--seed", type=int, default=42, help="Semente (reprodutibilidade)")
    parser.add_argument(
        "--saida", type=Path, default=Path("data/seed"), help="Diretório de saída"
    )
    args = parser.parse_args()

    rnd = random.Random(args.seed)
    fake = Faker("pt_BR")
    Faker.seed(args.seed)

    print(f"Gerando {args.motoristas} motoristas...")
    motoristas = gerar_motoristas(fake, rnd, args.motoristas)

    print(f"Gerando eventos de {args.dias} dias...")
    eventos = gerar_eventos(rnd, motoristas, args.dias, args.eventos_por_dia)

    print("Gerando de-para de regional...")
    de_para = gerar_de_para_regional(rnd, motoristas)

    escrever_json(args.saida / "motoristas.json", motoristas)
    escrever_json(args.saida / "eventos.json", eventos)
    escrever_csv(args.saida / "de_para_regional.csv", de_para)

    ativos = sum(1 for m in motoristas if m["active"])
    sem_regional = sum(1 for l in de_para if not l["regional"])

    print("\nConcluído.")
    print(f"  motoristas.json       {len(motoristas):>6} registros ({ativos} ativos)")
    print(f"  eventos.json          {len(eventos):>6} registros")
    print(f"  de_para_regional.csv  {len(de_para):>6} linhas ({sem_regional} sem regional)")
    print(f"\nArquivos em: {args.saida.resolve()}")
    print("Todos os dados são FICTÍCIOS. Nenhum dado pessoal ou corporativo real.")


if __name__ == "__main__":
    main()
