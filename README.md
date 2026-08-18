# Pipeline de Telemetria de Frota

Pipeline de dados que consolida telemetria de frota, cadastro de colaboradores e
classificação organizacional em um único banco analítico, com painéis de segurança
operacional construídos sobre ele.

**Stack:** Python · PostgreSQL · Docker · Metabase

> **Sobre os dados:** este repositório usa exclusivamente dados sintéticos, gerados
> pelo script incluído. Nenhum dado pessoal, operacional ou corporativo real é
> versionado aqui. A arquitetura é real; os dados não.

---

## O problema

Uma operação de campo com centenas de motoristas gera dados de segurança em três
lugares que não se conversam:

| Fonte | O que tem | O problema |
|---|---|---|
| API de telemetria | Eventos de direção (excesso de velocidade, frenagem brusca, uso de celular) | Não sabe a que regional o motorista pertence |
| Planilhas de cadastro | Matrícula, regional, centro de custo | Mantidas à mão, com lacunas e sem integração |
| Sistemas internos | Registros complementares de segurança | Cada um com seu próprio painel |

O resultado prático: cada gestor olha um painel diferente, ninguém consegue responder
"quais regionais concentram os eventos mais graves?" sem cruzar planilha na mão, e a
decisão chega atrasada em relação ao fato.

O gargalo não é falta de dado. É falta de conexão entre os dados.

---

## A solução

```
┌─────────────────┐
│  API telemetria │──┐
└─────────────────┘  │
                     │   ┌──────────┐   ┌────────────┐   ┌──────────┐
┌─────────────────┐  ├──▶│ Extração │──▶│ PostgreSQL │──▶│ Metabase │
│ Planilha regional│──┤   │  (Python)│   │  staging + │   │ (painéis)│
└─────────────────┘  │   └──────────┘   │   analytics│   └──────────┘
                     │                  └────────────┘
┌─────────────────┐  │
│ Fontes futuras  │──┘
└─────────────────┘
```

Três camadas, cada uma com uma responsabilidade única:

1. **Extração** — cada fonte tem seu próprio módulo, isolado. Trocar de fornecedor de
   telemetria não deve exigir mexer no resto do pipeline.
2. **Staging + transformação** — dados brutos entram como chegaram, sem perda. A
   limpeza e o cruzamento acontecem depois, em SQL, de forma auditável.
3. **Consumo** — painéis leem apenas as tabelas tratadas, nunca a fonte bruta.

---

## Decisões de arquitetura

**Por que Metabase e não Power BI?**
A organização não tinha licenças Power BI Pro, e o custo por usuário inviabilizava
distribuir painéis para toda a operação. O Metabase é open source, roda em container,
e o custo marginal de mais um usuário é zero. Trade-off aceito: menos recursos de
modelagem visual que o Power BI oferece.

**Por que PostgreSQL e não direto no BI?**
Conectar a ferramenta de BI diretamente nas APIs parece mais simples, mas amarra a
lógica de negócio dentro do painel — onde ela não é versionável nem testável. Com o
banco no meio, a regra de negócio vive em SQL sob controle de versão, e o painel vira
só apresentação.

**Por que Docker?**
O ambiente inteiro (banco + BI) sobe com um comando. Isso importou por um motivo
prático: o projeto começou como protótipo local antes de existir servidor aprovado.
Quando a infraestrutura veio, subir em outra máquina foi questão de rodar o mesmo
compose.

**Por que a regional vem de planilha e não da API?**
Porque na origem ela simplesmente não existe — o campo de agrupamento vem vazio na
prática. Em vez de fingir que o dado é limpo, o pipeline trata isso explicitamente:
existe um de-para, ele tem lacunas, e o modelo precisa lidar com motorista sem
regional atribuída. Esconder essa imperfeição tornaria o projeto mais bonito e menos
verdadeiro.

---

## Rodando o projeto

Pré-requisitos: Python 3.12+, Docker Desktop.

```bash
git clone https://github.com/vinibrum10/pipeline-telemetria-frota.git
cd pipeline-telemetria-frota

python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows
# source .venv/bin/activate       # Linux/macOS

pip install -r requirements.txt
python scripts/gerar_dados_fake.py
```

Isso gera, em `data/seed/`:

| Arquivo | Conteúdo |
|---|---|
| `motoristas.json` | 414 motoristas no formato da API de telemetria |
| `eventos.json` | ~8.500 eventos de direção ao longo de 90 dias |
| `de_para_regional.csv` | Mapeamento matrícula → regional (com lacunas propositais) |

Parâmetros: `--motoristas`, `--dias`, `--eventos-por-dia`, `--seed`.
A seed é fixa por padrão, então o dataset é reprodutível — quem clonar gera exatamente
os mesmos registros.

---

## Sobre os dados sintéticos

O gerador não produz dado aleatório uniforme. Ele reproduz três características do
dado real que importam para o resultado:

**Distribuição de Pareto nos eventos.** Uma minoria de motoristas concentra a maior
parte das ocorrências. Com distribuição uniforme, o painel de ranking não teria sinal
nenhum — todos empatariam, e o dashboard não serviria para decidir nada.

**Dado incompleto no de-para.** Cerca de 3% das linhas sem regional preenchida.
Planilha mantida à mão sempre tem buraco, e o pipeline precisa tratar isso.

**Campo de agrupamento vazio na API.** Replica a lacuna real que justifica a existência
do de-para.

CPFs são gerados com dígito verificador válido, mas fictícios — permitem exercitar
validação e formatação sem envolver nenhum documento real.

---

## Estado atual e próximos passos

Concluído:
- [x] Extração da API de telemetria
- [x] Carga em PostgreSQL (staging), com testes de lógica e qualidade de dado
- [x] Camada de marts (modelagem dimensional para consumo em painéis)
- [x] Ambiente containerizado (Postgres + Metabase)
- [x] Gerador de dados sintéticos

Em andamento:
- [ ] Painéis de segurança operacional no Metabase
- [ ] Log de execução e observabilidade
- [ ] Ingestão da segunda fonte (documentos corporativos via API)
- [ ] Orquestração e atualização periódica

---

## O que eu faria diferente

**Teria começado pelo modelo dimensional.** Comecei carregando dados brutos e pensando
na modelagem depois. Funcionou, mas refazer a estrutura de fatos e dimensões com dados
já carregados custou retrabalho que uma hora de desenho no início teria evitado.

**Teria separado dado real e dado de exemplo desde o primeiro commit.** O repositório
original nasceu com dados reais no histórico do Git, o que inviabilizou torná-lo
público — foi necessário recomeçar do zero. Histórico de Git é permanente; decidir
sobre dado sensível depois é decidir tarde demais.

**Ainda não resolvi a orquestração.** Hoje a atualização é manual. A escolha entre um
agendador simples e um orquestrador completo é a próxima decisão em aberto, e a
resposta honesta é que ainda não tenho volume suficiente para justificar a complexidade
do segundo.

---

## Contexto

Este projeto nasceu de um problema real que enfrentei liderando uma equipe de segurança
do trabalho no setor de energia: painéis que não se conversavam e decisões tomadas com
dado defasado. A versão publicada aqui é uma reconstrução com dados sintéticos,
preservando a arquitetura e as decisões técnicas.

**Vinícius Brum** — Engenheiro, atuando na interseção entre operação de infraestrutura
crítica e engenharia de dados.
[GitHub](https://github.com/vinibrum10)
