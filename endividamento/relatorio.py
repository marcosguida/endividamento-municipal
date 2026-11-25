"""Relatório consolidado da análise: tabelas (CSV + Excel) e gráficos (PNG).

Uso:  python -m endividamento.relatorio      ->  relatorios/
"""
from pathlib import Path
from typing import Dict

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .config import Settings, get_settings  # noqa: E402
from .dominio import LIMITE_ALERTA, resumo, resumo_por, serie_fpm, spearman  # noqa: E402
from .repository import MunicipioRepository  # noqa: E402

# Paleta: série única em azul, texto em tinta neutra, grade recessiva.
AZUL, TEXTO, TEXTO_2, GRADE, FUNDO = '#2a78d6', '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
plt.rcParams.update({
    'figure.facecolor': FUNDO, 'axes.facecolor': FUNDO, 'savefig.facecolor': FUNDO,
    'axes.edgecolor': GRADE, 'axes.labelcolor': TEXTO_2, 'text.color': TEXTO,
    'xtick.color': TEXTO_2, 'ytick.color': TEXTO_2, 'axes.grid': True, 'grid.color': GRADE,
    'grid.linewidth': 0.8, 'axes.axisbelow': True, 'axes.spines.top': False,
    'axes.spines.right': False, 'axes.titlesize': 12, 'axes.titleweight': 'bold', 'font.size': 10,
})


def tabelas(base: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    por_regiao = resumo_por(base, 'regiao').sort_values('dependencia.mediana_pct', ascending=False)
    por_regiao.loc['Brasil'] = resumo(base)
    alerta = (base[base['pct_dcl_rcl'] >= LIMITE_ALERTA]
              [['cod_ibge', 'municipio', 'uf', 'populacao', 'pct_dcl_rcl', 'dep_fpm']]
              .sort_values('pct_dcl_rcl', ascending=False).reset_index(drop=True))
    return {
        'por_regiao': por_regiao,
        'por_quintil': resumo_por(base, 'quintil_dep'),
        'por_porte': resumo_por(base, 'porte'),
        'regiao_x_porte_dc_rcl': base.pivot_table(index='regiao', columns='porte', values='dc_rcl',
                                                   aggfunc='median', observed=True),
        'lista_alerta': alerta,
        'serie_fpm': serie_fpm(base),
    }


def _barras(ax, rotulos, valores, titulo, fmt='{:.1f}%'):
    barras = ax.bar(rotulos, valores, color=AZUL, width=0.6)
    ax.bar_label(barras, [fmt.format(v).replace('.', ',') for v in valores], padding=3, color=TEXTO, fontsize=9)
    ax.set_title(titulo, loc='left')
    ax.grid(axis='x', visible=False)
    ax.margins(y=0.15)


def graficos(base: pd.DataFrame, t: Dict[str, pd.DataFrame], pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    q = t['por_quintil']

    # 1. Hipótese em duas medidas (dois gráficos, um eixo cada)
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4))
    _barras(a, q.index, q['divida.dc_rcl_mediana_pct'], 'Dívida bruta / RCL: mediana (%)')
    _barras(b, q.index, q['credito.municipios_com_operacao_pct'], 'Municípios que contrataram crédito (%)')
    for ax in (a, b):
        ax.set_xlabel('Quintil de dependência do FPM')
    fig.tight_layout()
    fig.savefig(pasta / '1_quintis_divida_credito.png', dpi=150)
    plt.close(fig)

    # 2. Região
    r = t['por_regiao'].drop('Brasil')['divida.municipios_dcl_positiva_pct'].sort_values()
    fig, ax = plt.subplots(figsize=(8, 3.6))
    barras = ax.barh(r.index, r.values, color=AZUL, height=0.6)
    ax.bar_label(barras, [f'{v:.0f}%' for v in r.values], padding=3, color=TEXTO, fontsize=9)
    ax.set_title('Municípios com dívida líquida positiva, por região (%)', loc='left')
    ax.grid(axis='y', visible=False)
    ax.margins(x=0.12)
    fig.tight_layout()
    fig.savefig(pasta / '2_regioes_dcl_positiva.png', dpi=150)
    plt.close(fig)

    # 3. Evolução do FPM
    s = t['serie_fpm']['fpm'] / 1e9
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(s.index, s.values, color=AZUL, linewidth=2, marker='o', markersize=5)
    for ano in (s.index[0], s.index[-1]):
        ax.annotate(f'R$ {s[ano]:.0f} bi', (ano, s[ano]), textcoords='offset points',
                    xytext=(0, 8), ha='center', color=TEXTO, fontsize=9)
    ax.set_title('FPM recebido pelos municípios (R$ bilhões, nominal)', loc='left')
    ax.set_xticks(s.index)
    ax.margins(y=0.15)
    fig.tight_layout()
    fig.savefig(pasta / '3_serie_fpm.png', dpi=150)
    plt.close(fig)

    # 4. Dispersão dependência × dívida
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.scatter(base['dep_fpm'] * 100, base['dc_rcl'].clip(upper=100), s=8, color=AZUL, alpha=0.35, linewidths=0)
    rho = spearman(base, 'dep_fpm', 'dc_rcl')
    ax.set_title(f'Dependência do FPM × dívida bruta/RCL (Spearman = {rho:.2f})'.replace('.', ','), loc='left')
    ax.set_xlabel('FPM / receita total (%)')
    ax.set_ylabel('Dívida bruta / RCL (%), cortado em 100')
    fig.tight_layout()
    fig.savefig(pasta / '4_dispersao_dependencia_divida.png', dpi=150)
    plt.close(fig)


def gerar(cfg: Settings) -> Dict[str, pd.DataFrame]:
    base = MunicipioRepository.from_csv(cfg.arquivo_base).filtrar().reset_index(drop=True)
    t = tabelas(base)
    pasta = cfg.saida_dir
    (pasta / 'tabelas').mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(pasta / f'relatorio_endividamento_{cfg.ano}.xlsx') as excel:
        for nome, df in t.items():
            df.round(2).to_excel(excel, sheet_name=nome[:31], index=nome != 'lista_alerta')
            df.round(2).to_csv(pasta / 'tabelas' / f'{nome}.csv', index=nome != 'lista_alerta')
    graficos(base, t, pasta / 'figuras')
    print(f'Relatório gerado em {pasta}')
    return t


if __name__ == '__main__':
    gerar(get_settings())
