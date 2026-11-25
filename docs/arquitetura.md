# Arquitetura e modelagem

Diagramas em [Mermaid](https://mermaid.js.org/), renderizados pelo próprio GitHub. Notação: C4 (contexto),
UML (classes e sequência) e modelo entidade-relacionamento (dados).

## 1. Contexto (C4)

De onde vêm os dados, o que o projeto produz e quem consome.

```mermaid
flowchart LR
    analista(["Pesquisador / analista"])

    subgraph fontes["Fontes públicas (Tesouro Nacional)"]
        tt[("Tesouro Transparente<br/>fpm-por-municipio.csv")]
        siconfi[("API SICONFI<br/>RGF Anexo 2 · DCA Anexo I-C")]
    end

    subgraph projeto["Radar Fiscal Municipal"]
        etl["ETL<br/>python -m endividamento.etl"]
        raw[("data/raw/<br/>brutos + cache JSON<br/>(fora do git)")]
        base[("data/processed/<br/>base_municipal_ANO.csv")]
        rel["Relatório<br/>python -m endividamento.relatorio"]
        out[("relatorios/<br/>tabelas CSV · Excel · gráficos PNG")]
        nb["Notebooks<br/>01 exploração · 02 análise"]
    end

    env[/".env<br/>(configuração, fora do git)"/]

    tt -- "download manual" --> raw
    siconfi -- "HTTP JSON (retry + pausa em 429)" --> etl
    raw --> etl
    etl -- "cache por município" --> raw
    etl -- "Load" --> base
    base --> rel --> out
    raw --> nb
    env -.-> etl
    env -.-> rel
    out --> analista
    nb --> analista
```

## 2. Camadas e dependências entre módulos

Cada seta é um `import`. O domínio não depende de nenhuma outra camada.

```mermaid
flowchart TB
    relatorio["relatorio.py<br/>tabelas e gráficos"]
    repo["repository.py<br/>acesso a dados"]
    etl["etl.py<br/>pipeline de dados"]
    dominio["dominio.py<br/>regras de negócio puras"]
    config["config.py<br/>Settings (.env)"]

    relatorio --> repo
    relatorio --> dominio
    relatorio --> config
    repo --> dominio
    etl --> dominio
    etl --> config

    classDef core fill:#e8f1ff,stroke:#3b6fd8,stroke-width:2px
    class dominio core
```

## 3. Diagrama de classes (UML)

```mermaid
classDiagram
    direction LR

    class Settings {
        +int ano
        +Path data_dir
        +Path saida_dir
        +str siconfi_api_url
        +int siconfi_workers
        +raw_dir() Path
        +arquivo_base() Path
    }

    class SiconfiClient {
        +str base_url
        -float _pausa_ate
        -Lock _trava
        +consultar(endpoint, **params) List~dict~
    }

    class Extrator {
        <<interface>>
        +__call__(api, ente, ano) List~dict~
    }
    class extrair_rgf {
        <<strategy>>
    }
    class extrair_dca {
        <<strategy>>
    }

    class MunicipioRepository {
        -DataFrame _df
        +from_csv(arquivo)$ MunicipioRepository
        +filtrar(uf, regiao, porte, quintil, nome, **intervalos) DataFrame
    }

    class Indicador {
        <<interface>>
        +__call__(df) dict
    }
    class INDICADORES {
        <<registry>>
        dependencia
        divida
        credito
        correlacao
    }

    class relatorio {
        <<module>>
        +tabelas(base) Dict~str,DataFrame~
        +graficos(base, tabelas, pasta)
        +gerar(cfg) Dict~str,DataFrame~
    }

    Extrator <|.. extrair_rgf
    Extrator <|.. extrair_dca
    extrair_rgf ..> SiconfiClient : usa
    extrair_dca ..> SiconfiClient : usa
    Settings <.. SiconfiClient : base_url

    INDICADORES o-- "4" Indicador : estratégias
    relatorio ..> MunicipioRepository : filtrar()
    relatorio ..> INDICADORES : resumo() / resumo_por()
    relatorio ..> Settings : saida_dir
```

## 4. Sequência: geração do relatório

```mermaid
sequenceDiagram
    autonumber
    actor A as Analista
    participant G as relatorio.gerar
    participant R as MunicipioRepository
    participant D as dominio
    participant FS as relatorios/

    A->>G: python -m endividamento.relatorio
    G->>R: from_csv(base_municipal_2025.csv)
    R-->>G: base (5.490 municípios)
    G->>D: resumo_por(base, "regiao" | "quintil_dep" | "porte")
    loop cada grupo
        D->>D: INDICADORES[nome](grupo)
    end
    D-->>G: DataFrames de indicadores
    G->>D: serie_fpm(base)
    D-->>G: FPM por ano
    G->>FS: tabelas/*.csv + relatorio_endividamento_2025.xlsx
    G->>FS: figuras/*.png
    G-->>A: Relatório gerado
```

## 5. Pipeline ETL

```mermaid
flowchart LR
    subgraph E["Extract"]
        a1[/"fpm-por-municipio.csv<br/>66.848 linhas · largo"/]
        a2[/"RGF Anexo 2<br/>387.985 linhas · longo"/]
        a3[/"DCA Anexo I-C<br/>712.990 linhas · longo"/]
    end

    subgraph T["Transform"]
        t1["transformar_fpm<br/>texto BR → número · sem DF<br/>só séries completas · melt"]
        t2["transformar_rgf<br/>posição 31/12 · pivot<br/>valida DCL = DC − Deduções<br/>regiao, porte, dc_rcl"]
        t3["transformar_dca<br/>receitas brutas · pivot<br/>dep_fpm = FPM / receita"]
        i1{"integrar<br/>RGF ⋈ DCA (cod_ibge)"}
        i2{"de-para SIAFI × IBGE<br/>nome normalizado + UF<br/>+ 22 correções"}
        i3["FPM anual (pivot)<br/>+ quintil_dep (qcut)"]
    end

    subgraph L["Load"]
        out[("base_municipal_2025.csv<br/>5.490 municípios × 31 colunas")]
    end

    a1 --> t1
    a2 --> t2
    a3 --> t3
    t2 --> i1
    t3 --> i1
    i1 --> i2
    t1 --> i2
    i2 --> i3 --> out
```

## 6. Modelo de dados (ER)

```mermaid
erDiagram
    FPM_MENSAL {
        string cod_siafi PK
        int ano PK
        int mes PK
        string municipio
        string uf
        float fpm "líquido, R$"
    }
    RGF_ANEXO2 {
        int cod_ibge PK
        string cod_conta PK
        string coluna PK
        string instituicao
        string uf
        int populacao
        float valor
    }
    DCA_ANEXO_IC {
        int cod_ibge PK
        string cod_conta PK
        string coluna PK
        float valor
    }
    BASE_MUNICIPAL {
        int cod_ibge PK
        int cod_siafi UK
        string municipio
        string uf
        string regiao
        string porte
        int populacao
        float dc
        float dcl
        float rcl
        float pct_dcl_rcl
        float dc_rcl
        float receita_total
        float impostos
        float fpm_dca
        float op_credito
        float dep_fpm
        string quintil_dep
        float fpm_2015_a_2025
    }

    RGF_ANEXO2 }o--|| BASE_MUNICIPAL : "pivot por cod_ibge"
    DCA_ANEXO_IC }o--|| BASE_MUNICIPAL : "pivot por cod_ibge"
    FPM_MENSAL }o--|| BASE_MUNICIPAL : "soma anual por cod_siafi"
```
