from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


BBox = tuple[float, float, float, float]  # x0, y0, x1, y1


def strip_font_subset(font: str) -> str:
    """ABCDEF+SimSun -> SimSun."""
    if "+" in font:
        return font.split("+", 1)[1]
    return font


@dataclass(slots=True)
class CharInfo:
    """One extracted character with style and position."""

    text: str
    font: str
    size: float
    color: int  # sRGB packed int from PyMuPDF
    bbox: BBox
    page: int
    block: int
    line: int
    span: int
    char_index: int  # global index within document index

    @property
    def font_display(self) -> str:
        return strip_font_subset(self.font)


@dataclass(slots=True)
class SpanInfo:
    text: str
    font: str
    size: float
    color: int
    bbox: BBox
    page: int
    block: int
    line: int
    span: int
    char_start: int
    char_end: int  # exclusive

    @property
    def font_display(self) -> str:
        return strip_font_subset(self.font)


class StyleMatchMode(str, Enum):
    FIRST_SPAN = "first_span"
    MAJORITY = "majority"
    ALL = "all"
    ANY = "any"


@dataclass
class StyleFilter:
    """Optional style predicates; None / empty means no constraint."""

    fonts: list[str] = field(default_factory=list)  # substring match on display name
    size_min: Optional[float] = None
    size_max: Optional[float] = None
    size_tolerance: float = 0.1
    colors: list[int] = field(default_factory=list)  # exact sRGB ints
    # page region in PDF coords (same as MuPDF); None = whole page
    region: Optional[BBox] = None
    match_mode: StyleMatchMode = StyleMatchMode.MAJORITY

    def is_empty(self) -> bool:
        return (
            not self.fonts
            and self.size_min is None
            and self.size_max is None
            and not self.colors
            and self.region is None
        )


@dataclass
class NormalizeOptions:
    strip_whitespace: bool = False
    unify_digits: bool = False  # reserved
    unify_dashes: bool = False  # reserved
    # Drop lone \n (soft wrap); keep a barrier for \n\n+ (blank line / page)
    collapse_single_newlines: bool = False

    def any_enabled(self) -> bool:
        return (
            self.strip_whitespace
            or self.unify_digits
            or self.unify_dashes
            or self.collapse_single_newlines
        )


@dataclass
class SearchQuery:
    pattern: str
    is_regex: bool = True
    case_insensitive: bool = False
    # Legacy name: means collapse soft newlines (not re.DOTALL)
    dotall: bool = False
    whole_word: bool = False  # require Unicode word boundaries around the match
    normalize: NormalizeOptions = field(default_factory=NormalizeOptions)
    style: StyleFilter = field(default_factory=StyleFilter)
    page_from: Optional[int] = None  # 0-based inclusive
    page_to: Optional[int] = None  # 0-based inclusive


@dataclass(slots=True)
class Hit:
    hit_id: int
    page: int
    text: str  # original matched text
    normalized_text: str  # after normalize rules (may equal text)
    bbox: BBox
    char_start: int
    char_end: int  # exclusive in document char list
    font: str
    size: float
    color: int
    reviewed: Optional[bool] = None  # True=ok, False=bad, None=unset

    @property
    def font_display(self) -> str:
        return strip_font_subset(self.font)


@dataclass
class DocumentIndex:
    path: str
    fingerprint: str
    page_count: int
    page_sizes: list[tuple[float, float]]  # width, height per page
    chars: list[CharInfo]
    spans: list[SpanInfo]
    # raw text with newlines between lines; stream_map[i] -> char_index or -1 for inserted \n
    raw_text: str
    stream_map: list[int]


class ViewMode(str, Enum):
    """Hit-tile viewport preset."""

    BOOK = "book"  # facing pages: even left, odd right; default
    FIT_WIDTH = "fit_width"  # full page width (horizontal books)
    FIT_HEIGHT = "fit_height"  # full page height (vertical books)
    LOCAL = "local"  # fixed window centered on hit (legacy)


class AlignMode(str, Enum):
    LEFT = "left"  # default for book / fit_width
    TOP = "top"  # default for fit_height
    CENTER = "center"  # default for local


class LayoutMode(str, Enum):
    """How hit tiles are arranged in the grid."""

    ROW = "row"  # left-to-right, then next row (横排)
    COLUMN = "column"  # top-to-bottom, then next column (竖排)


def default_align_for_view(mode: ViewMode) -> AlignMode:
    if mode in (ViewMode.BOOK, ViewMode.FIT_WIDTH):
        return AlignMode.LEFT
    if mode == ViewMode.FIT_HEIGHT:
        return AlignMode.TOP
    return AlignMode.CENTER


@dataclass
class CameraSettings:
    zoom: float = 2.0
    margin: float = 12.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    tile_w: int = 220
    tile_h: int = 120
    columns: int = 4  # lane count: columns when ROW, rows when COLUMN (ignored in BOOK)
    view_mode: ViewMode = ViewMode.BOOK
    align: AlignMode = AlignMode.LEFT
    layout: LayoutMode = LayoutMode.ROW
