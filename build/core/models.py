from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class FileQueryRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["file"]
    path: str


class InlineQueryRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["inline"]
    sql: str


QueryRef = Annotated[Union[FileQueryRef, InlineQueryRef], Field(discriminator="mode")]


class Layout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: int
    y: int
    w: int
    h: int


class FilterTargets(BaseModel):
    model_config = ConfigDict(extra="forbid")
    elements: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)


class FilterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension: str
    source: QueryRef
    default_value: list[str] | None = None
    targets: FilterTargets


class ElementBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    group_id: str | None = None
    layout: Layout
    # Free-form display config (title show/text/font, and - for cards - metric/
    # label fonts and alignment). A plain dict, like field_mapping, so builder
    # UI additions here never need a model change.
    style: dict = Field(default_factory=dict)


class ChartElement(ElementBase):
    type: Literal["chart"]
    subtype: Literal["line", "bar", "scatter", "combined", "area", "pie", "stacked_bar", "map"]
    query: QueryRef | None = None
    field_mapping: dict = Field(default_factory=dict)


class TableElement(ElementBase):
    type: Literal["table"]
    subtype: Literal["regular", "pivot", "grouped"]
    query: QueryRef | None = None
    field_mapping: dict = Field(default_factory=dict)


class CardElement(ElementBase):
    type: Literal["card"]
    query: QueryRef | None = None
    field_mapping: dict = Field(default_factory=dict)


class DropFilterElement(ElementBase):
    type: Literal["drop_filter"]
    subtype: Literal["single", "multiselect"]
    filter: FilterConfig


# Pure design elements - no query/field_mapping, never hit /api/data/element.
# All visual config (fill/border color, text content, font) lives in the
# free-form `style` dict on ElementBase, same as every other element's
# cosmetic settings.
class ShapeElement(ElementBase):
    type: Literal["shape"]
    subtype: Literal["rectangle", "circle"]


class TextElement(ElementBase):
    type: Literal["text"]


Element = Annotated[
    Union[ChartElement, TableElement, CardElement, DropFilterElement, ShapeElement, TextElement],
    Field(discriminator="type"),
]


class Group(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    shared_query: QueryRef | None = None
    element_ids: list[str] = Field(default_factory=list)
    color: str | None = None


class Tab(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    order: int = 0
    groups: list[Group] = Field(default_factory=list)
    elements: list[Element] = Field(default_factory=list)


class DashboardSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Fixed canvas width (px) elements are freely positioned/sized within,
    # slide-editor style - present once a dashboard has been opened in the
    # builder since free positioning replaced the grid-cell layout system.
    canvas_width: int | None = None
    # Legacy grid-cell settings, kept only so a pre-migration dashboard's
    # layout (still in grid-cell units at that point) can be converted to
    # pixels client-side on first load. Unused once canvas_width is set.
    grid_columns: int = 12
    row_height_px: int = 40
    # Path (relative to context/) of a .sql file to pre-fill as the query on
    # every newly-added chart/table/card/drop_filter, so the user doesn't
    # have to pick it by hand on each one for a dashboard built off a single
    # primary source. Purely a UI convenience - never affects already-placed
    # elements or is itself validated against file_registry (same trust
    # level as an element's own query path).
    default_query: str | None = None


class Dashboard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    schema_version: int = 1
    name: str
    created_at: str | None = None
    updated_at: str | None = None
    settings: DashboardSettings = Field(default_factory=DashboardSettings)
    tabs: list[Tab] = Field(default_factory=list)


class DashboardSummary(BaseModel):
    id: str
    name: str
    updated_at: str | None = None
