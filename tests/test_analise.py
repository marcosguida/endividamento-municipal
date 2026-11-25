"""Testes da análise contra os resultados publicados no notebook 02."""
import pandas as pd
import pytest
from pytest import approx

from endividamento.config import get_settings
from endividamento.dominio import normalizar, resumo, resumo_por, serie_fpm
from endividamento.relatorio import gerar
from endividamento.repository import MunicipioRepository


@pytest.fixture(scope='module')
def repo():
    return MunicipioRepository.from_csv(get_settings().arquivo_base)


def test_base_carregada(repo):
    assert len(repo) == 5490


def test_filtros(repo):
    assert len(repo.filtrar(regiao=['Norte'])) == 421
    assert len(repo.filtrar(pct_dcl_rcl_min=108)) == 42                     # lista de alerta
    assert repo.filtrar(nome='itaguatins')['municipio'].tolist() == ['Itaguatins']
    pequenos = repo.filtrar(populacao_max=19999, pct_dcl_rcl_min=50.0001)  # exceções à hipótese
    assert len(pequenos) == 167


def test_normalizar():
    assert normalizar(pd.Series(["Olho-d'Água"]))[0] == 'OLHO D AGUA'


def test_indicadores_brasil(repo):
    r = resumo(repo.filtrar())
    assert r['municipios'] == 5490
    assert r['dependencia.mediana_pct'] == approx(29.40, abs=0.01)
    assert r['divida.municipios_dcl_positiva_pct'] == approx(42.52, abs=0.01)
    assert r['correlacao.dependencia_x_dc_rcl'] == approx(-0.12, abs=0.005)


def test_gradiente_de_credito_por_quintil(repo):
    q = resumo_por(repo.filtrar(), 'quintil_dep', ['credito'])
    assert list(q.index) == ['Q1 (menor)', 'Q2', 'Q3', 'Q4', 'Q5 (maior)']
    assert list(q.columns) == ['municipios', 'populacao', 'fpm_ultimo_ano',
                               'credito.municipios_com_operacao_pct', 'credito.operacoes_sobre_receita_pct']
    credito = q['credito.municipios_com_operacao_pct']
    assert credito.iloc[0] == approx(35.73, abs=0.01) and credito.iloc[-1] == approx(11.21, abs=0.01)
    assert credito.is_monotonic_decreasing


def test_serie_fpm(repo):
    s = serie_fpm(repo.filtrar())
    assert list(s.index) == list(range(2015, 2026))
    assert pd.isna(s['variacao_pct'].iloc[0])


def test_relatorio_gera_arquivos(tmp_path):
    cfg = get_settings().model_copy(update={'saida_dir': tmp_path})
    gerar(cfg)
    assert len(list((tmp_path / 'tabelas').glob('*.csv'))) == 6
    assert len(list((tmp_path / 'figuras').glob('*.png'))) == 4
    assert (tmp_path / 'relatorio_endividamento_2025.xlsx').exists()
