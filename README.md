# PDFSearchViewer

图书PDF文字汇聚检查工具：搜索 PDF 文本，在统一视角的小窗中、在信息列表中集中比对命中项目，以发现同类项目是否一致，是否有缺漏。

搜索支持正则表达式、跨行、忽略空格等，可按字体、字号、字色等属性过滤。通过专项检查。

## 环境

- Windows，Python 3.11+
- 个人/内部使用（依赖 [PyMuPDF](https://pymupdf.readthedocs.io/)，AGPL）

```powershell
cd D:\ah21\PDFSearchViewer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

## 启动

```powershell
python -m pdfsearchviewer
```

或：

```powershell
pdfsearchviewer
```

## 用法概要

1. **打开 PDF**：工具栏「打开 PDF」。首次会建立字符级索引并写入本地 SQLite 缓存（`%USERPROFILE%\.pdfsearchviewer\cache.sqlite3`）。
2. **搜索**：左侧输入正则或普通文本。
   - **正则 / 忽略大小写 / `.` 匹配换行**：按需勾选。
   - **去掉空白后再匹配**：默认关闭。仅在图题、编号等「有空无空可算同类」时勾选；做空格体例检查时请保持关闭。
   - **样式过滤**：字体名子串、字号范围、字色（`#RRGGBB`）。
3. **集中浏览**：中间网格每个命中一个小窗。顶部可统一调整缩放、边距、平移、窗宽高、列数，点「应用视图」。
4. **统计**：右侧按原文/规范化形态、字体、字号、字色分组；点击行可筛选网格。
5. **复核**：小窗上勾选「正确 / 有误」；「保存会话」后复核状态会写入缓存。
6. **导出**：工具栏导出 CSV / JSON。

## 测试

```powershell
pytest
```

## 项目结构

```
src/pdfsearchviewer/
  indexer.py        # PyMuPDF 字符/样式索引
  normalize.py      # 可选规范化（去空白等）
  search_engine.py  # 搜索与样式谓词
  cache.py          # SQLite 缓存
  renderer.py       # 命中区域裁切渲染
  stats.py          # 分组统计
  ui/               # PySide6 界面
```

## 许可证说明

本工具依赖 PyMuPDF（AGPL）。仅适合个人或单位内部使用；若需对外分发闭源软件，请更换引擎或取得 Artifex 商用许可。

## TODO

* 限定坐标
* 页码偏置