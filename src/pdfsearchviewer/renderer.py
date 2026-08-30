from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtGui import QImage, QPainter, QColor, QPen

from .models import AlignMode, BBox, CameraSettings, Hit, ViewMode


def _view_size_pts(
    page_rect: pymupdf.Rect,
    camera: CameraSettings,
) -> tuple[float, float]:
    # BOOK uses the same clip geometry as FIT_WIDTH (full page width strip)
    if camera.view_mode in (ViewMode.BOOK, ViewMode.FIT_WIDTH):
        return page_rect.width, camera.tile_h / camera.zoom
    if camera.view_mode == ViewMode.FIT_HEIGHT:
        return camera.tile_w / camera.zoom, page_rect.height
    return camera.tile_w / camera.zoom, camera.tile_h / camera.zoom


def _clip_rect(
    hit_bbox: BBox,
    page_rect: pymupdf.Rect,
    camera: CameraSettings,
) -> pymupdf.Rect:
    hx0, hy0, hx1, hy1 = hit_bbox
    cx = (hx0 + hx1) / 2 + camera.pan_x
    cy = (hy0 + hy1) / 2 + camera.pan_y
    vw, vh = _view_size_pts(page_rect, camera)
    mode = camera.view_mode
    align = camera.align

    if mode in (ViewMode.BOOK, ViewMode.FIT_WIDTH):
        clip_x0 = page_rect.x0
        if align == AlignMode.TOP:
            clip_y0 = hy0 + camera.pan_y
        else:
            # LEFT / CENTER: vertically center on hit
            clip_y0 = cy - vh / 2
    elif mode == ViewMode.FIT_HEIGHT:
        clip_y0 = page_rect.y0
        if align == AlignMode.LEFT:
            clip_x0 = hx0 + camera.pan_x
        else:
            # TOP / CENTER: horizontally center on hit
            clip_x0 = cx - vw / 2
    else:
        # LOCAL
        if align == AlignMode.LEFT:
            clip_x0 = hx0 + camera.pan_x
            clip_y0 = cy - vh / 2
        elif align == AlignMode.TOP:
            clip_x0 = cx - vw / 2
            clip_y0 = hy0 + camera.pan_y
        else:
            clip_x0 = cx - vw / 2
            clip_y0 = cy - vh / 2

    clip = pymupdf.Rect(clip_x0, clip_y0, clip_x0 + vw, clip_y0 + vh)
    clip = clip & page_rect
    if clip.is_empty or clip.width < 1 or clip.height < 1:
        clip = pymupdf.Rect(
            max(page_rect.x0, hx0 - camera.margin),
            max(page_rect.y0, hy0 - camera.margin),
            min(page_rect.x1, hx1 + camera.margin),
            min(page_rect.y1, hy1 + camera.margin),
        )
    return clip


def _pad_offsets(
    img_w: int,
    img_h: int,
    tile_w: int,
    tile_h: int,
    align: AlignMode,
) -> tuple[int, int]:
    if align == AlignMode.LEFT:
        x = 0
        y = max(0, (tile_h - img_h) // 2)
    elif align == AlignMode.TOP:
        x = max(0, (tile_w - img_w) // 2)
        y = 0
    else:
        x = max(0, (tile_w - img_w) // 2)
        y = max(0, (tile_h - img_h) // 2)
    return x, y


def render_hit_image(
    doc: pymupdf.Document,
    hit: Hit,
    camera: CameraSettings,
    highlight: bool = True,
) -> QImage:
    page = doc[hit.page]
    page_rect = page.rect
    clip = _clip_rect(hit.bbox, page_rect, camera)
    mat = pymupdf.Matrix(camera.zoom, camera.zoom)
    pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
    fmt = QImage.Format.Format_RGB888
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()

    if highlight and not clip.is_empty:
        scale = camera.zoom
        hx0 = (hit.bbox[0] - clip.x0) * scale
        hy0 = (hit.bbox[1] - clip.y0) * scale
        hx1 = (hit.bbox[2] - clip.x0) * scale
        hy1 = (hit.bbox[3] - clip.y0) * scale
        painter = QPainter(img)
        painter.setPen(QPen(QColor(255, 80, 0, 220), 2))
        painter.fillRect(
            int(hx0),
            int(hy0),
            max(1, int(hx1 - hx0)),
            max(1, int(hy1 - hy0)),
            QColor(255, 200, 0, 80),
        )
        painter.drawRect(int(hx0), int(hy0), max(1, int(hx1 - hx0)), max(1, int(hy1 - hy0)))
        painter.end()

    if img.width() != camera.tile_w or img.height() != camera.tile_h:
        out = QImage(camera.tile_w, camera.tile_h, QImage.Format.Format_RGB888)
        out.fill(QColor(240, 240, 240))
        painter = QPainter(out)
        x, y = _pad_offsets(
            img.width(), img.height(), camera.tile_w, camera.tile_h, camera.align
        )
        painter.drawImage(x, y, img)
        painter.end()
        return out
    return img


class PdfRenderSession:
    """Keep a document open for repeated hit renders."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self.doc = pymupdf.open(self.path)

    def close(self) -> None:
        self.doc.close()

    def render(self, hit: Hit, camera: CameraSettings, highlight: bool = True) -> QImage:
        return render_hit_image(self.doc, hit, camera, highlight=highlight)

    def render_page(
        self,
        page_no: int,
        zoom: float,
        clip: pymupdf.Rect | None = None,
    ) -> QImage:
        page = self.doc[page_no]
        mat = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
        fmt = QImage.Format.Format_RGB888
        return QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()

    def page_rect(self, page_no: int) -> pymupdf.Rect:
        return self.doc[page_no].rect

    @property
    def page_count(self) -> int:
        return self.doc.page_count
