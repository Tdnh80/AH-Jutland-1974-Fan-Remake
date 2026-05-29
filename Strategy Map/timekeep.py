"""绝对游戏时间 <-> 回合 / 拍(substep) / HHMM / 日历日期。

内部以「绝对分钟」计时,epoch(第 0 分钟)默认 1916-05-31 00:00(日德兰海战当日)。
输出日期格式 DD/MM/YY HHMM(日/月/年)。
"""

from datetime import datetime, timedelta

EPOCH = datetime(1916, 5, 31, 0, 0)
MIN_PER_SUB = 10
SUB_PER_TURN = 6
MIN_PER_TURN = MIN_PER_SUB * SUB_PER_TURN   # 60


def turn_to_min(n):
    return n * MIN_PER_TURN


def sub_to_min(n):
    return n * MIN_PER_SUB


def min_to_turn(m):
    return m // MIN_PER_TURN


def min_to_sub(m):
    return m // MIN_PER_SUB


def hhmm_to_min(s):
    s = str(s).zfill(4)
    return int(s[:2]) * 60 + int(s[2:])


def fmt_clock(m):
    h = (m // 60) % 24
    return f"{h:02d}{m % 60:02d}"


def fmt_date(m, epoch=EPOCH):
    d = epoch + timedelta(minutes=m)
    return f"{d.day:02d}/{d.month:02d}/{d.year % 100:02d} {d.hour:02d}{d.minute:02d}"


def parse_time(token):
    """'T<n>'=回合, 'S<n>'/'sub<n>'=拍, 4 位数字=当日 HHMM。-> 绝对分钟。"""
    t = str(token).strip().lower()
    if t.startswith('t'):
        return turn_to_min(int(t[1:]))
    if t.startswith('sub'):
        return sub_to_min(int(t[3:]))
    if t.startswith('s'):
        return sub_to_min(int(t[1:]))
    return hhmm_to_min(t)
