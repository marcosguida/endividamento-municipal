"""Repository: único ponto que sabe onde e como a base municipal está guardada.

A API e as análises pedem municípios ao repositório e nunca leem arquivos
diretamente; trocar o CSV por um banco de dados muda só esta classe.
"""
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd

from .dominio import PORTES, QUINTIS, REGIOES, colunas_fpm, normalizar


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
        return df[m]

    def obter(self, cod_ibge: int) -> Optional[pd.DataFrame]:
        return self._df.loc[[cod_ibge]] if cod_ibge in self._df.index else None

    @staticmethod
    def para_registros(df: pd.DataFrame) -> List[dict]:
        """DataFrame -> lista de dicts JSON-friendly (NaN -> None, série do FPM agrupada)."""
        fpm = colunas_fpm(df)
        dados = df.drop(columns=['_nome', *fpm])
        registros = dados.astype(object).where(dados.notna(), None).to_dict(orient='records')
        for reg, serie in zip(registros, df[fpm].to_dict(orient='records')):
            reg['fpm'] = {int(c[4:]): v for c, v in serie.items()}
        return registros
