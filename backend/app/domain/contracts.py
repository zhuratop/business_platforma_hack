"""A0: shared external contracts. JSON values retain type internally."""
from typing import TypedDict, Literal, Any
from pydantic import BaseModel, Field

Source = Literal['BEFORE', 'AFTER']
ChangeType = Literal['SAME', 'VALUE_CHANGED', 'ATTRIBUTE_NEW', 'ATTRIBUTE_LOST']
RunState = Literal['QUEUED', 'NORMALIZING', 'COMPARING', 'FACTS', 'CHECKS', 'STATS', 'REPORTING', 'READY', 'FAILED']

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

DIMENSIONS = ['SOURCE', 'PREFIX', 'CLASS', 'SUFFIX', 'ARRAY_KEY', 'KEY', 'PATH',
              'VALUE_ADJUSTED', 'DIFF_FLAG', 'CHANGE_TYPE', 'product_id', 'partner_id',
              'DECISION_BEFORE', 'DECISION_AFTER', 'DECISION_CHANGED', 'PARTNER_TYPE', 'ROUTING_METHOD']

class PivotRequest(BaseModel):
    rows: list[str] = Field(default_factory=lambda: ['PATH'])
    columns: list[str] = Field(default_factory=lambda: ['CHANGE_TYPE'])
    filters: dict[str, list[Any]] = Field(default_factory=dict)
    measure: Literal['unique_apps'] = 'unique_apps'

class PivotCell(TypedDict):
    dimensions: dict[str, Any]
    count: int
    cell_token: str

class APIResponse(BaseModel):
    id: str | None = None
    status: str = 'ok'
    data: Any = None
