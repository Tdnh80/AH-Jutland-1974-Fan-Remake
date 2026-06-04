"""字母数字格名 <-> 内部 axial (q, r)。

映射由规则书搜索图确定:q = 数字, r = 字母行(A=1..Z=26, AA=27, BB=28, CC=29, DD=30)。
字母为「翻倍式」(A..Z 之后是 AA, BB, CC, DD),非 Excel 进位。
"""

import re

_CELL_RE = re.compile(r"^([A-Za-z]+)(-?\d+)$")


def idx_to_letter(i):
    if not 1 <= i <= 52:
        raise ValueError(f"row index out of range: {i}")
    if i <= 26:
        return chr(64 + i)
    return chr(64 + (i - 26)) * 2          # 27 -> AA, 28 -> BB, ...


def letter_to_idx(s):
    s = s.upper()
    if len(s) == 1 and 'A' <= s <= 'Z':
        return ord(s) - 64
    if len(s) == 2 and s[0] == s[1] and 'A' <= s[0] <= 'Z':
        return 26 + (ord(s[0]) - 64)       # AA -> 27, DD -> 30
    raise ValueError(f"bad letter row: {s!r}")


def parse_cell(label):
    """'A13' -> (q=13, r=1);  'DD-1' -> (q=-1, r=30)."""
    m = _CELL_RE.match(str(label).strip())
    if not m:
        raise ValueError(f"bad cell {label!r}; use e.g. A13, DD-1")
    return (int(m.group(2)), letter_to_idx(m.group(1)))


def cell_name(q, r):
    """(q=13, r=1) -> 'A13'."""
    return f"{idx_to_letter(r)}{q}"
