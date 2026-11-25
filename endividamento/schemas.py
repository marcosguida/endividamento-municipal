"""Contratos da API (entrada validada e saída documentada no OpenAPI / Swagger)."""
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from .dominio import INDICADORES, PORTES, QUINTIS, REGIAO, REGIOES

UF = Literal[tuple(sorted(REGIAO))]
Regiao = Literal[tuple(REGIOES)]
Porte = Literal[tuple(PORTES)]
Quintil = Literal[tuple(QUINTIS)]
NomeIndicador = Literal[tuple(INDICADORES)]
Dimensao = Literal['regiao', 'uf', 'porte', 'quintil_dep']
Ordenacao = Literal['pct_dcl_rcl', 'dc_rcl', 'dep_fpm', 'populacao', 'receita_total', 'op_credito', 'municipio']


class Filtros(BaseModel):
    """Filtros combináveis aceitos por /municipios, /indicadores e /fpm."""
    uf: List[UF] = Field(default_factory=list, description='Uma ou mais UFs (?uf=TO&uf=PA)')
    regiao: List[Regiao] = Field(default_factory=list)
    porte: List[Porte] = Field(default_factory=list, description='Faixa de população')
    quintil: List[Quintil] = Field(default_factory=list, description='Quintil de dependência do FPM')
    nome: Optional[str] = Field(None, max_length=100, description='Parte do nome, sem diferenciar acentos')
    dep_fpm_min: Optional[float] = Field(None, ge=0, le=1, description='FPM / receita total (0 a 1)')
    dep_fpm_max: Optional[float] = Field(None, ge=0, le=1)
    pct_dcl_rcl_min: Optional[float] = Field(None, description='DCL/RCL em %. Alerta: 108, limite legal: 120')
    pct_dcl_rcl_max: Optional[float] = None
    populacao_min: Optional[int] = Field(None, ge=0)
    populacao_max: Optional[int] = Field(None, ge=0)

    def criterios(self) -> dict:
        """Só os campos de filtro (sem paginação/ordenação das subclasses)."""
        return self.model_dump(include=set(Filtros.model_fields))


class ConsultaMunicipios(Filtros):
    ordenar: Ordenacao = 'pct_dcl_rcl'
    desc: bool = True
    limit: int = Field(50, ge=1, le=1000)
    offset: int = Field(0, ge=0)


class ConsultaIndicadores(Filtros):
    indicador: List[NomeIndicador] = Field(default_factory=list, description='Padrão: todos')


class Municipio(BaseModel):
    cod_ibge: int
    cod_siafi: int
    municipio: str
    uf: str
    regiao: str
    populacao: int
    porte: Optional[str]
    periodicidade: Optional[str] = Field(description='RGF quadrimestral (Q) ou semestral (S)')
    dc: Optional[float] = Field(description='Dívida Consolidada (R$)')
    deducoes: Optional[float]
    dcl: Optional[float] = Field(description='Dívida Consolidada Líquida (R$)')
    rcl: Optional[float] = Field(description='Receita Corrente Líquida ajustada (R$)')
    pct_dcl_rcl: Optional[float] = Field(description='DCL / RCL (%)')
    dc_rcl: Optional[float] = Field(description='Dívida bruta / RCL (%)')
    receita_total: Optional[float]
    impostos: Optional[float]
    fpm_dca: Optional[float] = Field(description='FPM bruto declarado na DCA (R$)')
    op_credito: Optional[float] = Field(description='Operações de crédito no ano (R$)')
    dep_fpm: Optional[float] = Field(description='FPM / receita total (0 a 1)')
    quintil_dep: Optional[str]
    fpm: Dict[int, float] = Field(description='FPM líquido recebido por ano (Tesouro, R$ nominais)')


class Pagina(BaseModel):
    total: int
    limit: int
    offset: int
    itens: List[Municipio]


class Dependencia(BaseModel):
    mediana_pct: Optional[float]
    municipios_alta_dependencia_pct: Optional[float] = Field(description='% com FPM ≥ 40% da receita')


class Divida(BaseModel):
    dcl_rcl_mediana_pct: Optional[float]
    dc_rcl_mediana_pct: Optional[float]
    municipios_dcl_positiva_pct: Optional[float]
    municipios_acima_alerta_pct: Optional[float] = Field(description='% com DCL/RCL ≥ 108%')
    municipios_acima_limite_pct: Optional[float] = Field(description='% com DCL/RCL > 120%')


class Credito(BaseModel):
    municipios_com_operacao_pct: Optional[float]
    operacoes_sobre_receita_pct: Optional[float]


class Correlacao(BaseModel):
    dependencia_x_dc_rcl: Optional[float] = Field(description='Spearman; negativo apoia a hipótese')
    dependencia_x_dcl_rcl: Optional[float]


class Resumo(BaseModel):
    municipios: int
    populacao: int
    fpm_ultimo_ano: Optional[float]
    dependencia: Optional[Dependencia] = None
    divida: Optional[Divida] = None
    credito: Optional[Credito] = None
    correlacao: Optional[Correlacao] = None


class PontoFPM(BaseModel):
    ano: int
    fpm: float
    variacao_pct: Optional[float]
