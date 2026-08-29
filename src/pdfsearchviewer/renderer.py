from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtGui import QImage, QPainter, QColor, QPen

from .models import BBox, CameraSettings, Hit


def _clip_rect(
    hit_bbox: BBox,
    page_rect: pymupdf.Rect,
    camera: CameraSettings,
) -> pymupdf.Rect:
    x0, y0, x1, y1 = hit_bbox
    cx = (x0 + x1) / 2 + camera.pan_x
    cy = (y0 + y1) / 2 + camera.pan_y
    # Desired view size in PDF points from tile pixels / zoom
    view_w = camera.tile_w / camera.zoom
    view_h = camera.tile_h / camera.zoom
    # Also expand by margin around hit
    half_w = max(view_w / 2, (x1 - x0) / 2 + camera.margin)
    half_h = max(view_h / 2, (y1 - y0) / 2 + camera.margin)
    # Prefer fixed tile aspect: use view_w/view_h as primary
    half_w = view_w / 2
    half_h = view_h / 2
    clip = pymupdf.Rect(cx - half_w, cy - half_h, cx + half_w, cy + half_h)
    # Clamp to page
    clip = clip & page_rect
    if clip.is_empty or clip.width < 1 or clip.height < 1:
        # fallback: hit bbox + margin
        clip = pymupdf.Rect(
            max(page_rect.x0, x0 - camera.margin),
            max(page_rect.y0, y0 - camera.margin),
            min(page_rect.x1, x1 + camera.margin),
            min(page_rect.y1, y1 + camera.margin),
        )
    return clip


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
        # Map hit bbox to image coords
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

    # Scale/pad to exact tile size
    if img.width() != camera.tile_w or img.height() != camera.tile_h:
        out = QImage(camera.tile_w, camera.tile_h, QImage.Format.Format_RGB888)
        out.fill(QColor(240, 240, 240))
        painter = QPainter(out)
        x = (camera.tile_w - img.width()) // 2
        y = (camera.tile_h - img.height()) // 2
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
