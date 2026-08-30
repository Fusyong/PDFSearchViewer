"""Local character-class escapes for search patterns (Python ``re`` dialect).

Extensions (expanded before compile):

- ``\\y`` / ``\\Y`` — pinyin letters (and complement)
- ``\\c`` / ``\\C`` — Han ideographs (and complement)
- ``\\p`` / ``\\P`` — common Chinese punctuation (and complement)
- ``\\j`` / ``\\J`` — Chinese numerals (and complement)

Outside ``[]``, each expands to a character class (``\\Y`` → ``[^…]``).
Inside ``[]``, positive escapes inject class contents;
complement escapes are not valid inside ``[]``.
"""

from __future__ import annotations

# Product-specified pinyin letter set (Latin + tone-marked vowels / nasals).
PINYIN_CHARS = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "āáǎàōóǒòêê̄ếê̌ềēéěèīíǐìūúǔùüǖǘǚǜm̄ḿm̀ńňǹẑĉŝŋ"
    "ĀÁǍÀŌÓǑÒÊÊ̄ẾÊ̌ỀĒÉĚÈĪÍǏÌŪÚǓÙÜǕǗǙǛM̄ḾM̀ŃŇǸẐĈŜŊ"
)

# CJK Unified Ideographs + Ext. A + Compatibility Ideographs (+ 〇)
HAN_CLASS_BODY = (
    "\u3007"
    "\u3400-\u4dbf"
    "\u4e00-\u9fff"
    "\uf900-\ufaff"
)

# Product-specified Chinese punctuation
CJK_PUNCT_CHARS = "。，、；：？！「」『』“”‘’（）—～…《》〈〉·"

# Product-specified Chinese numerals (汉字数字)
HAN_NUMERAL_CHARS = "〇一二三四五六七八九十百千万亿兆"

LOCALE_ESCAPE_HELP = (
    "本地字符集转义（在 Python re 之上扩展）：\n"
    "\n"
    "  \\y  拼音字母\n"
    "  \\Y  非拼音字母（\\y 的补集）\n"
    "  \\c  汉字\n"
    "  \\C  非汉字（\\c 的补集）\n"
    "  \\p  中文标点\n"
    "  \\P  非中文标点（\\p 的补集）\n"
    "  \\j  汉字数字（〇一二三四五六七八九十百千万亿兆）\n"
    "  \\J  非汉字数字（\\j 的补集）\n"
    "\n"
    "示例：\\c+ 连续汉字；\\j+ 连续汉字数字；\\y+ 拼音串；[^\\p] 非中文标点（也可用 \\P）。\n"
    "注意：\\Y / \\C / \\P / \\J 请写在字符类 [] 外。"
)


def _escape_class_char(ch: str) -> str:
    if ch in "\\^[]-":
        return "\\" + ch
    return ch


def _chars_to_class_body(chars: str) -> str:
    return "".join(_escape_class_char(ch) for ch in chars)


PINYIN_BODY = _chars_to_class_body(PINYIN_CHARS)
CJK_PUNCT_BODY = _chars_to_class_body(CJK_PUNCT_CHARS)
HAN_NUMERAL_BODY = _chars_to_class_body(HAN_NUMERAL_CHARS)

_ESCAPE_BODY: dict[str, str] = {
    "y": PINYIN_BODY,
    "Y": PINYIN_BODY,
    "c": HAN_CLASS_BODY,
    "C": HAN_CLASS_BODY,
    "p": CJK_PUNCT_BODY,
    "P": CJK_PUNCT_BODY,
    "j": HAN_NUMERAL_BODY,
    "J": HAN_NUMERAL_BODY,
}
_COMPLEMENT = frozenset("YCPJ")
_COMPLEMENT_TO_POS = {"Y": "y", "C": "c", "P": "p", "J": "j"}


def _odd_backslashes_before(s: str, idx: int) -> bool:
    k = 0
    j = idx - 1
    while j >= 0 and s[j] == "\\":
        k += 1
        j -= 1
    return k % 2 == 1


def expand_locale_escapes(pattern: str) -> str:
    """Expand ``\\y\\Y\\c\\C\\p\\P\\j\\J`` in a Python-``re`` pattern string."""
    out: list[str] = []
    i = 0
    n = len(pattern)
    in_class = False

    while i < n:
        ch = pattern[i]

        if ch == "\\" and i + 1 < n:
            nxt = pattern[i + 1]
            if nxt in _ESCAPE_BODY:
                body = _ESCAPE_BODY[nxt]
                neg = nxt in _COMPLEMENT
                if in_class:
                    if neg:
                        pos = _COMPLEMENT_TO_POS[nxt]
                        raise ValueError(
                            f"\\{nxt} 不能写在字符类 [] 内部；"
                            f"请把 \\{nxt} 写在 [] 外，或写成 [^\\{pos}]"
                        )
                    out.append(body)
                else:
                    out.append(f"[^{body}]" if neg else f"[{body}]")
                i += 2
                continue
            out.append(ch)
            out.append(nxt)
            i += 2
            continue

        if ch == "[" and not _odd_backslashes_before(pattern, i):
            if not in_class:
                in_class = True
            out.append(ch)
            i += 1
            continue

        if ch == "]" and in_class and not _odd_backslashes_before(pattern, i):
            in_class = False
            out.append(ch)
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)
