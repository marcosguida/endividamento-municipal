"""Configuração lida de variáveis de ambiente / arquivo `.env` (nunca versionado)."""
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=RAIZ / '.env', extra='ignore')

    ano: int = 2025
    data_dir: Path = RAIZ / 'data'
    siconfi_api_url: str = 'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/'
    siconfi_workers: int = 4
    cors_origins: List[str] = ['*']

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / 'raw'

    @property
    def arquivo_base(self) -> Path:
        return self.data_dir / 'processed' / f'base_municipal_{self.ano}.csv'


@lru_cache
def get_settings() -> Settings:
    return Settings()
