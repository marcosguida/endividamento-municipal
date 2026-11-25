# Endividamento Municipal × Dependência do FPM

API e pipeline de dados para analisar a **dívida dos municípios brasileiros** frente aos limites da
Lei de Responsabilidade Fiscal e a **dependência do Fundo de Participação dos Municípios (FPM)**.

> **Hipótese:** municípios mais dependentes do FPM têm menor endividamento (DCL/RCL), por terem
> menos capacidade própria de pagamento e menos acesso a crédito.

Projeto da disciplina *Fundamentos de Programação Científica* (CST em Sistemas para Internet, IFTO, Campus Palmas).

## Principais resultados (exercício 2025, 5.490 municípios)

| Achado | Evidência |
|---|---|
| A hipótese se confirma **só em parte** | Spearman dependência × dívida bruta/RCL = **−0,12** (fraca). O quintil mais dependente tem a menor dívida, mas os quintis Q2 a Q4 ficam parecidos |
| O acesso a crédito explica o mecanismo | Municípios com operação de crédito: **36% (Q1) → 11% (Q5)** |
| A região muda o resultado | Nordeste e Sudeste têm a mesma dependência (~31%), mas o Nordeste tem 74% dos municípios com DCL positiva, contra 28% no Sudeste |
| O endividamento excessivo é localizado | 57% têm caixa maior que a dívida; só **42** passam do alerta de 108% |

A análise completa está em [notebooks/02_analise_indicadores.ipynb](notebooks/02_analise_indicadores.ipynb).

## Arquitetura

Os diagramas completos (C4, camadas, classes UML, sequência, ETL e modelo ER) estão em [docs/arquitetura.md](docs/arquitetura.md).

```
Tesouro Transparente (FPM) ─┐
SICONFI API (RGF, DCA) ─────┼─► etl.py ─► data/processed/base_municipal_2025.csv
                            │   Extract → Transform → Load
                            │
              repository.py ◄── lê a base processada
                    │
              dominio.py      (indicadores, regras da LRF; funções puras)
                    │
               api.py  ──►  FastAPI  ──►  /docs (Swagger)
```

```
endividamento/
├── config.py       # Settings a partir do .env
├── dominio.py      # constantes legais, classificações e indicadores (sem I/O)
├── etl.py          # pipeline: API SICONFI + CSV do FPM → base integrada
├── repository.py   # acesso e filtros sobre a base municipal
├── schemas.py      # contratos de entrada e saída (Pydantic)
└── api.py          # rotas HTTP
data/processed/     # base pronta (versionada); data/raw/ fica fora do git
notebooks/          # 01 exploração e seleção, 02 análise e indicadores
tests/              # testes da API contra os resultados do notebook
```

### Design patterns

| Padrão | Onde | Por quê |
|---|---|---|
| **Repository** | `MunicipioRepository` | A API não sabe se os dados vêm de CSV ou de um banco; trocar o armazenamento muda só essa classe |
| **Strategy + Registry** | `dominio.INDICADORES` e os extratores `extrair_rgf`/`extrair_dca` | Cada indicador é uma função intercambiável; um indicador novo passa a existir na API quando é registrado (`?indicador=divida`). O ETL recebe o extrator como parâmetro |
| **Pipeline (ETL)** | `etl.executar` | Etapas isoladas e testáveis: `transformar_fpm`, `transformar_rgf`, `transformar_dca`, `integrar` |
| **Dependency Injection** | `Depends(get_repo)` | As rotas recebem o repositório; nos testes, dá para trocá-lo por `app.dependency_overrides` |
| **Singleton (cache)** | `@lru_cache` em `get_settings`/`get_repo` | Configuração e base carregadas uma vez por processo |
| **DTO** | `schemas.py` | Valida a entrada (UF, região e faixas inválidas viram 422) e documenta a saída no OpenAPI |

## Como usar

```bash
git clone https://github.com/marcosguida/endividamento-municipal.git && cd endividamento-municipal
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # opcional: os valores padrão já funcionam

uvicorn endividamento.api:app --reload
# abra http://127.0.0.1:8000/docs
```

Testes: `pytest`

### Endpoints

| Método e rota | Descrição |
|---|---|
| `GET /health` | Status e número de municípios carregados |
| `GET /municipios` | Lista paginada com filtros e ordenação |
| `GET /municipios/{cod_ibge}` | Dados de um município, com a série anual do FPM |
| `GET /indicadores` | Indicadores I1–I4 da seleção (Brasil, se não houver filtro) |
| `GET /indicadores/{dimensao}` | Indicadores por `regiao`, `uf`, `porte` ou `quintil_dep` |
| `GET /fpm/serie` | FPM total por ano da seleção e variação anual |

**Filtros** (aceitos por todas as rotas de consulta, combináveis): `uf`, `regiao`, `porte`, `quintil`,
`nome`, `dep_fpm_min/max` (0–1), `pct_dcl_rcl_min/max` (%), `populacao_min/max`.

```bash
# Lista de alerta: DCL/RCL ≥ 108%
curl "localhost:8000/municipios?pct_dcl_rcl_min=108"

# Municípios do Tocantins muito dependentes do FPM, menos endividados primeiro
curl "localhost:8000/municipios?uf=TO&dep_fpm_min=0.4&ordenar=pct_dcl_rcl&desc=false"

# Só os indicadores de crédito, por quintil de dependência
curl "localhost:8000/indicadores/quintil_dep?indicador=credito"

# Indicadores do Nordeste, por porte
curl "localhost:8000/indicadores/porte?regiao=Nordeste"
```

### Indicadores

| Indicador | Mede |
|---|---|
| **I1 `dependencia`** | Mediana de FPM/receita total e % de municípios com FPM ≥ 40% da receita |
| **I2 `divida`** | Medianas de DCL/RCL e DC/RCL e % acima do alerta (108%) e do limite legal (120%) |
| **I3 `credito`** | % de municípios que contrataram crédito e crédito/receita do grupo |
| **I4 `correlacao`** | Spearman entre dependência e dívida (negativo apoia a hipótese) |

## Atualizar os dados (ETL)

1. Baixe `fpm-por-municipio.csv` em [Tesouro Transparente, Transferências a Estados e Municípios](https://www.tesourotransparente.gov.br/temas/estados-e-municipios/transferencias-a-estados-e-municipios) e salve em `data/raw/`.
2. Ajuste `ANO` no `.env`, se quiser outro exercício.
3. Rode:

```bash
python -m endividamento.etl
```

O RGF (Anexo 2) e a DCA (Anexo I-C) são baixados da [API do SICONFI](https://apidatalake.tesouro.gov.br/docs/siconfi/)
(cerca de 5.570 municípios, com cache por município; leva algumas horas por causa do limite de requisições).
O resultado substitui `data/processed/base_municipal_<ANO>.csv`.

## Fontes

| Base | Fonte | Chave |
|---|---|---|
| FPM mensal, 2015–2025 | Tesouro Transparente (CSV) | código SIAFI |
| RGF, Anexo 2: DC, DCL, RCL, % DCL/RCL | API SICONFI | código IBGE |
| DCA, Anexo I-C: receitas, FPM, operações de crédito | API SICONFI | código IBGE |

Todos são dados públicos do Tesouro Nacional. A ligação SIAFI × IBGE é feita pelo nome normalizado + UF,
com 22 correções manuais (`etl.CORRECOES_NOME`).

## Limitações

- Os dados são **autodeclarados** no SICONFI: valores como 1.333% de DCL/RCL indicam erro de preenchimento. Por isso a análise usa mediana e Spearman.
- É o retrato de um ano: mostra **associação, não causalidade**. O porte do município é uma variável de confusão.
- O FPM está em valores **nominais**. O do Tesouro é líquido (sem o FUNDEB) e o da DCA é bruto.
- Ficam de fora o DF e os municípios que não entregaram o RGF e a DCA (79 de 5.569).
