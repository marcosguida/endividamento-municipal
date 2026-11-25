"""Testes da API contra a base processada; valores esperados = relatório do notebook 02."""
from fastapi.testclient import TestClient
from pytest import approx

from endividamento.api import app

client = TestClient(app)


def test_health():
    assert client.get('/health').json()['municipios'] == 5490


def test_filtros_e_paginacao():
    r = client.get('/municipios', params={'regiao': 'Norte', 'limit': 5}).json()
    assert r['total'] == 421 and len(r['itens']) == 5
    assert all(m['regiao'] == 'Norte' for m in r['itens'])
    dcl = [m['pct_dcl_rcl'] for m in r['itens']]
    assert dcl == sorted(dcl, reverse=True)


def test_lista_alerta():
    assert client.get('/municipios', params={'pct_dcl_rcl_min': 108}).json()['total'] == 42


def test_busca_por_nome_sem_acento():
    nomes = [m['municipio'] for m in client.get('/municipios', params={'nome': 'itaguatins'}).json()['itens']]
    assert nomes == ['Itaguatins']


def test_detalhe_e_404():
    m = client.get('/municipios/3503406').json()
    assert m['municipio'] == 'Arealva' and m['fpm'][str(2025)] == approx(15979817.8)
    assert client.get('/municipios/1').status_code == 404


def test_validacao_de_entrada():
    assert client.get('/municipios', params={'uf': 'XX'}).status_code == 422
    assert client.get('/indicadores/cidade').status_code == 422


def test_indicadores_brasil():
    r = client.get('/indicadores').json()
    assert r['municipios'] == 5490
    assert r['dependencia']['mediana_pct'] == approx(29.40, abs=0.01)
    assert r['divida']['municipios_dcl_positiva_pct'] == approx(42.52, abs=0.01)
    assert r['correlacao']['dependencia_x_dc_rcl'] == approx(-0.12, abs=0.005)


def test_indicadores_por_quintil_e_selecao():
    r = client.get('/indicadores/quintil_dep', params={'indicador': 'credito'}).json()
    assert list(r) == ['Q1 (menor)', 'Q2', 'Q3', 'Q4', 'Q5 (maior)']
    assert r['Q1 (menor)']['credito']['municipios_com_operacao_pct'] == approx(35.73, abs=0.01)
    assert r['Q5 (maior)']['credito']['municipios_com_operacao_pct'] == approx(11.21, abs=0.01)
    assert 'divida' not in r['Q1 (menor)']


def test_serie_fpm():
    serie = client.get('/fpm/serie').json()
    assert [p['ano'] for p in serie] == list(range(2015, 2026))
    assert serie[0]['variacao_pct'] is None
