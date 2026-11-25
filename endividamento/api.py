"""API HTTP (FastAPI). Rodar:  uvicorn endividamento.api:app --reload   ->  /docs"""
from functools import lru_cache
from typing import Annotated, Dict, List

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .dominio import resumo, resumo_por, serie_fpm
from .repository import MunicipioRepository
from .schemas import (ConsultaIndicadores, ConsultaMunicipios, Dimensao, Filtros, Municipio, Pagina,
                      PontoFPM, Resumo)

app = FastAPI(
    title='API de Endividamento Municipal',
    version=__version__,
    description='Dívida (SICONFI/RGF), receitas (SICONFI/DCA) e FPM (Tesouro) dos municípios brasileiros, '
                'com indicadores de dependência do FPM e situação fiscal frente aos limites da LRF.',
)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=['GET'])


@lru_cache
def get_repo() -> MunicipioRepository:
    # Carregado uma vez por processo; nos testes pode ser trocado via app.dependency_overrides.
    return MunicipioRepository.from_csv(get_settings().arquivo_base)


Repo = Annotated[MunicipioRepository, Depends(get_repo)]


@app.get('/health')
def health(repo: Repo):
    return {'status': 'ok', 'ano': get_settings().ano, 'municipios': len(repo)}


@app.get('/municipios', response_model=Pagina)
def listar_municipios(repo: Repo, q: Annotated[ConsultaMunicipios, Query()]):
    """Lista paginada. Ex.: lista de alerta = `?pct_dcl_rcl_min=108`."""
    df = repo.filtrar(**q.criterios()).sort_values(q.ordenar, ascending=not q.desc)
    return Pagina(total=len(df), limit=q.limit, offset=q.offset,
                  itens=repo.para_registros(df.iloc[q.offset:q.offset + q.limit]))


@app.get('/municipios/{cod_ibge}', response_model=Municipio)
def obter_municipio(repo: Repo, cod_ibge: int):
    df = repo.obter(cod_ibge)
    if df is None:
        raise HTTPException(404, f'Município {cod_ibge} não encontrado')
    return repo.para_registros(df)[0]


@app.get('/indicadores', response_model=Resumo, response_model_exclude_none=True)
def indicadores(repo: Repo, q: Annotated[ConsultaIndicadores, Query()]):
    """Indicadores I1–I4 para a seleção filtrada (Brasil, se nenhum filtro)."""
    return resumo(repo.filtrar(**q.criterios()), q.indicador)


@app.get('/indicadores/{dimensao}', response_model=Dict[str, Resumo], response_model_exclude_none=True)
def indicadores_por(repo: Repo, dimensao: Dimensao, q: Annotated[ConsultaIndicadores, Query()]):
    """Indicadores agrupados por região, UF, porte ou quintil de dependência."""
    return resumo_por(repo.filtrar(**q.criterios()), dimensao, q.indicador)


@app.get('/fpm/serie', response_model=List[PontoFPM])
def fpm_serie(repo: Repo, q: Annotated[Filtros, Query()]):
    """FPM total recebido por ano pela seleção (R$ nominais)."""
    return serie_fpm(repo.filtrar(**q.criterios()))
