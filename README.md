# PDFSearchViewer

图书PDF文字汇聚检查工具：搜索 PDF 文本，在统一视角的小窗中、在信息列表中集中比对命中项目，以发现同类项目是否一致，是否有缺漏。

搜索支持正则表达式（含汉字、拼音等中文常用字符集）、跨行、忽略空格等，可按字体、字号、字色等属性过滤。通过专项检查。

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
2. **搜索**：左侧输入正则或普通文本，点「搜索」只按文本匹配（含下方规范化选项）。
   - **正则 / 忽略大小写 / 整词匹配 / 忽略单个换行**：按需勾选。「整词匹配」要求匹配两侧不是英文字母、数字或下划线。「忽略单个换行」会去掉软换行以便跨行匹配，但保留空行（两个及以上换行）作为分隔。
   - **本地字符集转义**（勾选正则时可用）：`\y`/`\Y` 拼音字母及其补集，`\c`/`\C` 汉字及其补集，`\p`/`\P` 中文标点及其补集，`\j`/`\J` 汉字数字（〇一二三四五六七八九十百千万亿兆）及其补集。菜单「帮助 → 本地字符集转义…」有说明；完整语法见「帮助 → 正则表达式语法（Python re）…」。
   - **忽略空白**：默认关闭。忽略搜索字符串和页面文本两侧的空白字符后再匹配；做空格体例检查时请保持关闭。
3. **呈现过滤**（改条件即刷新列表，**不**重新搜索）：
   - **样式过滤**：字体名子串、字号范围、字色（`#RRGGBB`）。
   - **坐标过滤**：PDF 点矩形（命中框中心落入区域内才显示）；也可在「页面浏览」中框选填入。
   - **页码过滤**：按偏置后的图书页码范围显示。
   - **页码偏置**：整数（可为负）。界面与导出中的页码均为「图书页码 = PDF 页（1-based）+ 偏置」。
4. **命中聚合**：中间「命中聚合」标签。视窗可选**书籍**（默认，左右对页：左双码、右单码，无命中留空）/全宽/全高/局部；对齐与横排·竖排·排数可调（书籍模式固定两列对页）；点「应用视图」。
5. **页面浏览**：中间「页面浏览」标签。视图/缩放快捷键对齐 SumatraPDF（`Ctrl+0/1/2/3`、`+/-`、`z`、`c` 等）。可拾取文字属性或框选坐标并写回过滤选项。单击命中会联动翻页；双击命中小窗跳到浏览页。
6. **统计**：右侧按原文/规范化形态、字体、字号、字色分组（基于当前呈现结果）；点击行可筛选网格。
7. **复核**：小窗上勾选「正确 / 有误」；「保存会话」后复核状态会写入缓存。
8. **导出**：工具栏导出 CSV / JSON（完整搜索结果，含图书页码与偏置）。

## 测试

```powershell
pytest
```

## 打包为 exe

在项目根目录执行（会使用 `.venv`，自动安装 PyInstaller）：

```powershell
.\build_exe.ps1
```

或双击 / 命令行运行 `build_exe.bat`。

成功后得到单文件：

```text
dist\PDFSearchViewer.exe
```

可选参数：

```powershell
.\build_exe.ps1 -Clean          # 先清空 build/、dist/
.\build_exe.ps1 -Onedir         # 打成文件夹（启动更快，便于排查依赖）
```

说明：需在 Windows 本机打包；产物体积主要来自 PyMuPDF 与 PySide6。目标机器无需安装 Python。

## 项目结构

```
src/pdfsearchviewer/
  indexer.py        # PyMuPDF 字符/样式索引
  normalize.py      # 可选规范化（去空白等）
  search_engine.py  # 搜索与样式谓词
  page_numbers.py   # 图书页码 ↔ PDF 页换算
  cache.py          # SQLite 缓存
  renderer.py       # 命中区域裁切渲染
  stats.py          # 分组统计
  ui/               # PySide6 界面
```

## 许可证说明

本工具依赖 PyMuPDF（AGPL）。仅适合个人或单位内部使用；若需对外分发闭源软件，请更换引擎或取得 Artifex 商用许可。

## 后续

* 页面浏览：真正的连续多页长卷（当前 `c` 仅切换状态标记）
* 页面浏览：Facing / 多栏页视图
