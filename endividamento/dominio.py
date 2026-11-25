"""Regras de negócio puras (sem I/O): constantes legais, classificações e indicadores.

Cada indicador é uma *estratégia* (função `DataFrame -> dict`) registrada em
`INDICADORES`. Qualquer seleção de municípios (Brasil, região, filtro do usuário)
passa pelas mesmas funções; para criar um indicador novo, basta registrá-lo.
"""
import math
from typing import Callable, Dict, Iterable, Optional

import pandas as pd

REGIAO = {**dict.fromkeys(['AC', 'AP', 'AM', 'PA', 'RO', 'RR', 'TO'], 'Norte'),
          **dict.fromkeys(['AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE'], 'Nordeste'),
          **dict.fromkeys(['DF', 'GO', 'MT', 'MS'], 'Centro-Oeste'),
          **dict.fromkeys(['ES', 'MG', 'RJ', 'SP'], 'Sudeste'),
          **dict.fromkeys(['PR', 'RS', 'SC'], 'Sul')}
REGIOES = ['Norte', 'Nordeste', 'Centro-Oeste', 'Sudeste', 'Sul']
PORTES = ['até 10 mil', '10–20 mil', '20–50 mil', '50–100 mil', '100–500 mil', '> 500 mil']
LIMITES_PORTE = [0, 10_000, 20_000, 50_000, 100_000, 500_000, math.inf]
QUINTIS = ['Q1 (menor)', 'Q2', 'Q3', 'Q4', 'Q5 (maior)']

LIMITE_ALERTA, LIMITE_LEGAL = 108, 120   # % DCL/RCL (LRF + Resolução do Senado nº 40/2001)
LIMIAR_DEP = 0.40                        # "alta dependência": FPM ≥ 40% da receita total


def normalizar(nomes: pd.Series) -> pd.Series:
    """"Olho-d'Água" -> "OLHO D AGUA" (sem acento, maiúsculo, espaços simples)."""
    return (nomes.str.normalize('NFKD').str.encode('ascii', 'ignore').str.decode('ascii')
                 .str.upper().str.replace(r"[-']", ' ', regex=True).str.split().str.join(' '))


def colunas_fpm(df: pd.DataFrame) -> list:
    return sorted(c for c in df.columns if c.startswith('fpm_') and c[4:].isdigit())


# --- Indicadores (estratégias) -------------------------------------------------

def ind_dependencia(df: pd.DataFrame) -> dict:
    dep = df['dep_fpm'].dropna()
    return {'mediana_pct': dep.median() * 100,
            'municipios_alta_dependencia_pct': (dep >= LIMIAR_DEP).mean() * 100}


def ind_divida(df: pd.DataFrame) -> dict:
    dcl = df['pct_dcl_rcl'].dropna()
    return {'dcl_rcl_mediana_pct': dcl.median(),
            'dc_rcl_mediana_pct': df['dc_rcl'].median(),
            'municipios_dcl_positiva_pct': (dcl > 0).mean() * 100,
            'municipios_acima_alerta_pct': (dcl >= LIMITE_ALERTA).mean() * 100,
            'municipios_acima_limite_pct': (dcl > LIMITE_LEGAL).mean() * 100}


def ind_credito(df: pd.DataFrame) -> dict:
    return {'municipios_com_operacao_pct': (df['op_credito'] > 0).mean() * 100,
            'operacoes_sobre_receita_pct': df['op_credito'].sum() / df['receita_total'].sum() * 100}


def spearman(df: pd.DataFrame, x: str, y: str) -> float:
    # Pearson entre as posições (rank): não é distorcida por valores extremos.
    par = df[[x, y]].dropna()
    return par[x].rank().corr(par[y].rank())


def ind_correlacao(df: pd.DataFrame) -> dict:
    return {'dependencia_x_dc_rcl': spearman(df, 'dep_fpm', 'dc_rcl'),
            'dependencia_x_dcl_rcl': spearman(df, 'dep_fpm', 'pct_dcl_rcl')}


Indicador = Callable[[pd.DataFrame], dict]
INDICADORES: Dict[str, Indicador] = {
    'dependencia': ind_dependencia,
    'divida': ind_divida,
    'credito': ind_credito,
    'correlacao': ind_correlacao,
}


def _sem_nan(d):
    if isinstance(d, dict):
        return {k: _sem_nan(v) for k, v in d.items()}
    return None if isinstance(d, float) and math.isnan(d) else d


def resumo(df: pd.DataFrame, nomes: Optional[Iterable[str]] = None) -> dict:
    """Totais do grupo + os indicadores pedidos (todos, se `nomes` for None)."""
    fpm = colunas_fpm(df)
    saida = {'municipios': len(df),
             'populacao': int(df['populacao'].sum()),
             'fpm_ultimo_ano': float(df[fpm[-1]].sum()) if fpm else None}
    for nome in (nomes or INDICADORES):
        saida[nome] = INDICADORES[nome](df)
    return _sem_nan(saida)


def resumo_por(df: pd.DataFrame, dimensao: str, nomes: Optional[Iterable[str]] = None) -> dict:
    return {str(grupo): resumo(g, nomes) for grupo, g in df.groupby(dimensao, observed=True)}


def serie_fpm(df: pd.DataFrame) -> list:
    """FPM total por ano (R$ nominais) e variação anual."""
    total = df[colunas_fpm(df)].sum()
    variacao = total.pct_change() * 100
    return [{'ano': int(c[4:]), 'fpm': float(v), 'variacao_pct': _sem_nan(float(variacao[c]))}
            for c, v in total.items()]
