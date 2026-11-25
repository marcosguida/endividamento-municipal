"""Pipeline ETL: Extract (Tesouro/SICONFI) -> Transform (pandas) -> Load (CSV processado).

Uso:  python -m endividamento.etl

- FPM: baixe `fpm-por-municipio.csv` no Tesouro Transparente e coloque em `data/raw/`.
- RGF e DCA: baixados da API pública do SICONFI (com cache por município em `data/raw/`).
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, List

import pandas as pd

from .config import Settings, get_settings
from .dominio import LIMITES_PORTE, PORTES, QUINTIS, REGIAO, REGIOES, normalizar

ANO_INICIAL_FPM = 2015


# --- Extract -----------------------------------------------------------------

class SiconfiClient:
    """Cliente da API pública do SICONFI: repete em caso de falha e pausa todas as
    threads por 30 s quando a API responde 429 (limite de requisições)."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._pausa_ate = 0.0
        self._trava = threading.Lock()

    def consultar(self, endpoint: str, **params) -> List[dict]:
        url = self.base_url + endpoint + '?' + urllib.parse.urlencode(params)
        for _ in range(12):
            time.sleep(max(0, self._pausa_ate - time.time()))
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    return json.load(r)['items']
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    with self._trava:
                        self._pausa_ate = time.time() + 30
                else:
                    time.sleep(5)
            except Exception:
                time.sleep(5)
        raise RuntimeError(f'Falha: {endpoint} {params.get("id_ente")}')


Extrator = Callable[[SiconfiClient, dict, int], List[dict]]


def extrair_rgf(api: SiconfiClient, ente: dict, ano: int) -> List[dict]:
    quadrimestral = dict(in_periodicidade='Q', nr_periodo=3, co_tipo_demonstrativo='RGF')
    semestral = dict(in_periodicidade='S', nr_periodo=2, co_tipo_demonstrativo='RGF Simplificado')
    # Municípios < 50 mil hab. podem optar pelo RGF semestral: tenta o mais provável primeiro.
    formatos = [semestral, quadrimestral] if (ente['populacao'] or 0) < 50000 else [quadrimestral, semestral]
    for f in formatos:
        itens = api.consultar('rgf', an_exercicio=ano, no_anexo='RGF-Anexo 02', co_esfera='M',
                              co_poder='E', id_ente=ente['cod_ibge'], **f)
        if itens:
            return itens
    return []


def extrair_dca(api: SiconfiClient, ente: dict, ano: int) -> List[dict]:
    return api.consultar('dca', an_exercicio=ano, no_anexo='DCA-Anexo I-C', id_ente=ente['cod_ibge'])


def carregar_siconfi(arquivo: Path, extrair: Extrator, api: SiconfiClient, ano: int, workers: int) -> pd.DataFrame:
    """Lê o CSV já extraído; se não existir, baixa da API (cache JSON por município)."""
    if arquivo.exists():
        return pd.read_csv(arquivo, sep=';')
    cache = arquivo.with_suffix('')
    cache.mkdir(parents=True, exist_ok=True)
    entes = [e for e in api.consultar('entes') if e['esfera'] == 'M']

    def tarefa(ente):
        destino = cache / f'{ente["cod_ibge"]}.json'
        if not destino.exists():
            destino.write_text(json.dumps(extrair(api, ente, ano)))

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(tarefa, entes))
    linhas = [item for e in entes for item in json.loads((cache / f'{e["cod_ibge"]}.json').read_text())]
    df = pd.DataFrame(linhas)
    df.to_csv(arquivo, sep=';', index=False)
    return df


# --- Transform ---------------------------------------------------------------

def _texto_para_numero(serie: pd.Series) -> pd.Series:
    # ' 50.880,73 ' -> 50880.73 ; '-' (sem repasse) -> NaN
    return pd.to_numeric(serie.str.strip().str.replace('.', '', regex=False)
                              .str.replace(',', '.', regex=False), errors='coerce')


def transformar_fpm(fpm_original: pd.DataFrame, ano: int) -> pd.DataFrame:
    """Formato largo (ano em colunas) -> longo: uma linha por município e mês."""
    anos = [str(a) for a in range(ANO_INICIAL_FPM, ano + 1)]
    fpm = fpm_original[['COD_MUN', 'Município', 'UF', 'Mês'] + anos].copy()
    fpm[anos] = fpm[anos].apply(_texto_para_numero)
    fpm = fpm[fpm['COD_MUN'].notna() & (fpm['UF'] != 'DF')]
    fpm = fpm[fpm[anos].notna().all(axis=1).groupby(fpm['COD_MUN']).transform('all')]  # só séries completas
    longo = (fpm.melt(id_vars=['COD_MUN', 'Município', 'UF', 'Mês'], var_name='ano', value_name='fpm')
                .rename(columns={'COD_MUN': 'cod_siafi', 'Município': 'municipio', 'UF': 'uf', 'Mês': 'mes'})
                .astype({'ano': int, 'mes': int}))
    assert not longo.duplicated(['cod_siafi', 'ano', 'mes']).any()
    return longo


CONTAS_RGF = {'DividaConsolidada': 'dc', 'DeducoesDaDividaConsolidada': 'deducoes',
              'DividaConsolidadaLiquida': 'dcl',
              'ReceitaCorrenteLiquidaAjustadaParaCalculoDosLimitesDeEndividamento': 'rcl',
              'PercentualDaDCLSobreARCL': 'pct_dcl_rcl'}
FECHAMENTO = ['Até o 3º Quadrimestre', 'Até o 2º Semestre']  # posição em 31/12


def transformar_rgf(rgf_original: pd.DataFrame) -> pd.DataFrame:
    rgf = rgf_original[rgf_original['coluna'].isin(FECHAMENTO) & rgf_original['cod_conta'].isin(CONTAS_RGF)]
    divida = (rgf[['cod_ibge', 'instituicao', 'uf', 'populacao', 'periodicidade']].drop_duplicates('cod_ibge')
                 .merge(rgf.pivot(index='cod_ibge', columns='cod_conta', values='valor').rename(columns=CONTAS_RGF),
                        on='cod_ibge'))
    # A API omite contas sem valor; DCL = DC − Deduções confirma que ausente = 0.
    identidade = (divida['dc'].fillna(0) - divida['deducoes'].fillna(0) - divida['dcl']).abs() < 1
    if not identidade[divida['dcl'].notna()].all():
        print('Aviso: DCL ≠ DC − Deduções em', (~identidade).sum(), 'municípios')
    divida[['dc', 'deducoes']] = divida[['dc', 'deducoes']].fillna(0)
    divida['municipio'] = divida['instituicao'].str.replace(r'^Prefeitura Municipal d[eoa]s? | - [A-Z]{2}$', '', regex=True)
    divida['regiao'] = pd.Categorical(divida['uf'].map(REGIAO), categories=REGIOES)
    divida['porte'] = pd.cut(divida['populacao'], LIMITES_PORTE, labels=PORTES)
    divida['dc_rcl'] = divida['dc'] / divida['rcl'] * 100   # dívida bruta / RCL (%)
    return divida.drop(columns='instituicao')


CONTAS_DCA = {'TotalReceitas': 'receita_total', 'RO1.1.0.0.00.0.0': 'impostos',
              'RO1.7.1.1.51.0.0': 'fpm_dca', 'RO2.1.0.0.00.0.0': 'op_credito'}


def transformar_dca(dca_original: pd.DataFrame) -> pd.DataFrame:
    dca = dca_original[(dca_original['coluna'] == 'Receitas Brutas Realizadas')
                       & dca_original['cod_conta'].isin(CONTAS_DCA)]
    receitas = dca.pivot(index='cod_ibge', columns='cod_conta', values='valor').rename(columns=CONTAS_DCA).reset_index()
    receitas.columns.name = None
    receitas['op_credito'] = receitas['op_credito'].fillna(0)           # sem a linha = não contratou crédito
    receitas['dep_fpm'] = receitas['fpm_dca'] / receitas['receita_total']
    return receitas


# Municípios com nome diferente no IBGE (SICONFI) e no SIAFI (FPM): (UF, nome IBGE) -> nome SIAFI
CORRECOES_NOME = {
    ('SP', 'Embu das Artes'): 'Embu', ('SP', 'Mogi Mirim'): 'Moji Mirim', ('RJ', 'Paraty'): 'Parati',
    ('RJ', 'Trajano de Moraes'): 'Trajano de Morais', ('MG', 'Brazópolis'): 'Brasópolis',
    ('MG', 'São Tomé das Letras'): 'São Thomé das Letras', ('CE', 'Itapajé'): 'Itapagé',
    ('PB', 'São Domingos'): 'São Domingos de Pombal', ('PB', 'São Vicente do Seridó'): 'Seridó',
    ('PE', 'Belém do São Francisco'): 'Belém de São Francisco', ('PE', 'Iguaracy'): 'Iguaraci',
    ('PE', 'Lagoa de Itaenga'): 'Lagoa do Itaenga', ('RN', 'Campo Grande'): 'Augusto Severo',
    ('RN', 'Boa Saúde'): 'Januário Cicco', ('RN', 'Serra Caiada'): 'Presidente Juscelino',
    ('MT', 'Poxoréu'): 'Poxoréo', ('PA', 'Eldorado do Carajás'): 'Eldorado dos Carajás',
    ('PA', 'Santa Izabel do Pará'): 'Santa Isabel do Pará', ('TO', 'Couto Magalhães'): 'Couto de Magalhães',
    ('TO', 'Tabocão'): 'Fortaleza do Tabocão', ('TO', 'São Valério'): 'São Valério da Natividade',
    ('RS', "Sant'Ana do Livramento"): 'Santana do Livramento',
}


def integrar(divida: pd.DataFrame, receitas: pd.DataFrame, fpm_longo: pd.DataFrame) -> pd.DataFrame:
    """RGF × DCA (código IBGE) e × FPM (de-para SIAFI por nome normalizado + UF)."""
    base = divida.merge(receitas, on='cod_ibge', how='inner', validate='one_to_one')

    siafi = fpm_longo[['cod_siafi', 'municipio', 'uf']].drop_duplicates('cod_siafi')
    siafi['chave'] = normalizar(siafi['municipio'])
    base['chave'] = normalizar(pd.Series([CORRECOES_NOME.get((uf, m), m)
                                          for uf, m in zip(base['uf'], base['municipio'])]))
    base = base.merge(siafi[['cod_siafi', 'chave', 'uf']], on=['chave', 'uf'], how='left',
                      validate='one_to_one', indicator=True)
    sem_par = base.loc[base['_merge'] == 'left_only', ['municipio', 'uf']].values.tolist()
    if sem_par:
        print('Sem correspondência no FPM (descartados):', sem_par)
    base = base[base['_merge'] == 'both'].drop(columns=['chave', '_merge']).reset_index(drop=True)

    anual = fpm_longo.pivot_table(index='cod_siafi', columns='ano', values='fpm', aggfunc='sum').add_prefix('fpm_')
    base = base.merge(anual.reset_index(), on='cod_siafi', how='left', validate='one_to_one')
    base['cod_siafi'] = base['cod_siafi'].astype(int)
    base['quintil_dep'] = pd.qcut(base['dep_fpm'], 5, labels=QUINTIS)
    assert base['cod_ibge'].is_unique
    return base


# --- Load / orquestração -------------------------------------------------------

def executar(cfg: Settings) -> pd.DataFrame:
    raw = cfg.raw_dir
    api = SiconfiClient(cfg.siconfi_api_url)
    print('1/4 Lendo FPM...')
    fpm = pd.read_csv(raw / 'fpm-por-municipio.csv', sep=';', encoding='latin1', dtype={'COD_MUN': str})
    print('2/4 RGF Anexo 2 (SICONFI)...')
    rgf = carregar_siconfi(raw / f'siconfi_rgf_anexo02_municipios_{cfg.ano}.csv', extrair_rgf, api, cfg.ano, cfg.siconfi_workers)
    print('3/4 DCA Anexo I-C (SICONFI)...')
    dca = carregar_siconfi(raw / f'siconfi_dca_anexoIC_municipios_{cfg.ano}.csv', extrair_dca, api, cfg.ano, cfg.siconfi_workers)
    print('4/4 Transformando e integrando...')
    base = integrar(transformar_rgf(rgf), transformar_dca(dca), transformar_fpm(fpm, cfg.ano))
    cfg.arquivo_base.parent.mkdir(parents=True, exist_ok=True)
    base.to_csv(cfg.arquivo_base, index=False)
    print(f'OK: {len(base)} municípios -> {cfg.arquivo_base}')
    return base


if __name__ == '__main__':
    executar(get_settings())
