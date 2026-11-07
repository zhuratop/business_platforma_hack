"""A0: shared external contracts. JSON values retain type internally."""
from typing import TypedDict, Literal, Any, Protocol
from pydantic import BaseModel, Field

Source = Literal['BEFORE', 'AFTER']
ChangeType = Literal['SAME', 'VALUE_CHANGED', 'ATTRIBUTE_NEW', 'ATTRIBUTE_LOST']
RunState = Literal['QUEUED', 'READING', 'NORMALIZING', 'COMPARING', 'FACTS', 'CHECKS', 'STATS', 'REPORTING', 'PAUSED', 'READY', 'FAILED']

class InputReader(Protocol):
    def __call__(self, raw: bytes, filename: str, app_id: str, source: Source, params: dict) -> dict:
        """Decode one source file to a JSON-compatible application object."""
        ...

class NormalizedRow(TypedDict):
    APP_ID: str
    SOURCE: Source
    PREFIX: str
    CLASS: str
    SUFFIX: str
    ARRAY_KEY: str
    KEY: str
    PATH: str
    VALUE: str
    ADJUSTED_VALUE: str
    VALUE_KIND: str

class ComparisonRow(TypedDict):
    APP_ID: str
    PREFIX: str
    CLASS: str
    SUFFIX: str
    ARRAY_KEY: str
    KEY: str
    PATH: str
    VALUE_BEFORE: str
    VALUE_AFTER: str
    ADJUSTED_BEFORE: str
    ADJUSTED_AFTER: str
    DIFF_FLAG: int
    CHANGE_TYPE: ChangeType

class Segment(TypedDict):
    APP_ID: str
    DECISION_BEFORE: str
    DECISION_AFTER: str
    DECISION_CHANGED: int
    PRODUCTS: str
    TOP_OFFER_BEFORE: str
    TOP_OFFER_AFTER: str
    PARTNER_TYPE: str
    ROUTING_METHOD: str
    PD_MODEL_BEFORE: str
    PD_MODEL_AFTER: str
    CUTOFF_BEFORE: str
    CUTOFF_AFTER: str
    REJECT_REASON_BEFORE: str
    REJECT_REASON_AFTER: str
    SCORE_OKB_BEFORE: str
    SCORE_OKB_AFTER: str

class Fact(TypedDict):
    SOURCE: Source
    PREFIX: str
    CLASS: str
    SUFFIX: str
    ARRAY_KEY: str
    KEY: str
    PATH: str
    VALUE_ADJUSTED: str
    DIFF_FLAG: int
    CHANGE_TYPE: ChangeType
    product_id: str
    partner_id: str
    CNT: int
    APP_IDS: list[str]

FACT_DIMENSIONS = ['SOURCE', 'PREFIX', 'CLASS', 'SUFFIX', 'ARRAY_KEY', 'KEY', 'PATH',
              'VALUE_ADJUSTED', 'DIFF_FLAG', 'CHANGE_TYPE', 'product_id', 'partner_id',
              'DECISION_BEFORE', 'DECISION_AFTER', 'DECISION_CHANGED', 'PARTNER_TYPE', 'ROUTING_METHOD']
DIMENSIONS = FACT_DIMENSIONS + ['ADJUSTED_BEFORE', 'ADJUSTED_AFTER']
DIMENSION_GROUPS = {
    'Основные': ['PATH','SOURCE','CHANGE_TYPE','VALUE_ADJUSTED','ADJUSTED_BEFORE','ADJUSTED_AFTER'],
    'Бизнес-разрезы': ['product_id','partner_id','DECISION_BEFORE','DECISION_AFTER','PARTNER_TYPE','ROUTING_METHOD'],
    'Признаки для фильтрации': ['DIFF_FLAG','DECISION_CHANGED'],
    'Технические': ['PREFIX','CLASS','SUFFIX','KEY','ARRAY_KEY'],
}
DIMENSION_LABELS = {
    'PATH':'Атрибут', 'SOURCE':'Срез', 'CHANGE_TYPE':'Тип изменения', 'VALUE_ADJUSTED':'Значение / бакет среза',
    'ADJUSTED_BEFORE':'Бакет до', 'ADJUSTED_AFTER':'Бакет после', 'product_id':'Продукт', 'partner_id':'Партнёр',
    'DECISION_BEFORE':'Решение заявки до', 'DECISION_AFTER':'Решение заявки после',
    'PARTNER_TYPE':'Набор типов партнёров заявки', 'ROUTING_METHOD':'Набор маршрутов заявки',
    'DIFF_FLAG':'Есть различие', 'DECISION_CHANGED':'Решение заявки изменилось',
    'PREFIX':'Начало пути', 'CLASS':'Класс', 'SUFFIX':'Продолжение пути', 'KEY':'Имя поля', 'ARRAY_KEY':'Ключи массивов',
}

class PivotRequest(BaseModel):
    rows: list[str] = Field(default_factory=lambda: ['PATH'])
    columns: list[str] = Field(default_factory=lambda: ['CHANGE_TYPE'])
    filters: dict[str, list[Any]] = Field(default_factory=dict)
    measure: Literal['unique_apps'] = 'unique_apps'
    page: int = Field(default=1, ge=1)
    page_size: int | None = Field(default=None, ge=1, le=250)
    include_totals: bool = False
    collapse_unchanged: bool = False

class PivotCell(TypedDict):
    dimensions: dict[str, Any]
    count: int
    cell_token: str

class APIResponse(BaseModel):
    id: str | None = None
    status: str = 'ok'
    data: Any = None
