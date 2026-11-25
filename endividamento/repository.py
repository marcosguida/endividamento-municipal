"""Repository: único ponto que sabe onde e como a base municipal está guardada.

Relatórios, testes e notebooks pedem municípios ao repositório e nunca leem
arquivos diretamente; trocar o CSV por um banco de dados muda só esta classe.
"""
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from .dominio import PORTES, QUINTIS, REGIOES, normalizar


class MunicipioRepository:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    @classmethod
    def from_csv(cls, arquivo: Path) -> 'MunicipioRepository':
        if not arquivo.exists():
            raise FileNotFoundError(f'{arquivo} não existe. Rode: python -m endividamento.etl')
        df = pd.read_csv(arquivo)
        for col, categorias in (('regiao', REGIOES), ('porte', PORTES), ('quintil_dep', QUINTIS)):
            df[col] = pd.Categorical(df[col], categories=categorias, ordered=True)
        df['_nome'] = normalizar(df['municipio'])
        return cls(df.set_index('cod_ibge', drop=False))

    def __len__(self) -> int:
        return len(self._df)

    def filtrar(self, uf: Optional[Iterable[str]] = None, regiao: Optional[Iterable[str]] = None,
                porte: Optional[Iterable[str]] = None, quintil: Optional[Iterable[str]] = None,
                nome: Optional[str] = None, **intervalos: Optional[float]) -> pd.DataFrame:
        """Filtros combináveis (E lógico). `intervalos`: `<coluna>_min` / `<coluna>_max`."""
        df = self._df
        m = pd.Series(True, index=df.index)
        for col, valores in (('uf', uf), ('regiao', regiao), ('porte', porte), ('quintil_dep', quintil)):
            if valores:
                m &= df[col].isin(list(valores))
        if nome:
            m &= df['_nome'].str.contains(normalizar(pd.Series([nome]))[0], regex=False)
        for chave, valor in intervalos.items():
            if valor is None:
                continue
            col, lado = chave.rsplit('_', 1)
            m &= df[col] >= valor if lado == 'min' else df[col] <= valor
        return df[m].drop(columns='_nome')
