"""Curated administrative-division data (GB/T 2260) for coherent generation.

Provides a small but *real* set of 6-digit region codes mapped to their
province / city / district names.  Used both by the ID-card generator (the
first 6 digits of a mainland China ID encode the region) and by the
cross-field coherence pass (so a row's 省/市/区县 fields form a real hierarchy
instead of an impossible combination like "广东省 + 北京市 + 浦东新区").
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    code: str        # 6-digit GB/T 2260 code
    province: str
    city: str
    district: str


# A compact, real spread across several provinces. Jining (济宁) entries are
# included because the working dataset is Jining open data.
REGIONS: tuple[Region, ...] = (
    Region("110101", "北京市", "北京市", "东城区"),
    Region("110105", "北京市", "北京市", "朝阳区"),
    Region("120101", "天津市", "天津市", "和平区"),
    Region("310101", "上海市", "上海市", "黄浦区"),
    Region("310115", "上海市", "上海市", "浦东新区"),
    Region("500103", "重庆市", "重庆市", "渝中区"),
    Region("370102", "山东省", "济南市", "历下区"),
    Region("370811", "山东省", "济宁市", "任城区"),
    Region("370812", "山东省", "济宁市", "兖州区"),
    Region("370881", "山东省", "济宁市", "曲阜市"),
    Region("370883", "山东省", "济宁市", "邹城市"),
    Region("370831", "山东省", "济宁市", "微山县"),
    Region("370202", "山东省", "青岛市", "市南区"),
    Region("440103", "广东省", "广州市", "荔湾区"),
    Region("440304", "广东省", "深圳市", "福田区"),
    Region("320102", "江苏省", "南京市", "玄武区"),
    Region("320583", "江苏省", "苏州市", "昆山市"),
    Region("330102", "浙江省", "杭州市", "上城区"),
    Region("510104", "四川省", "成都市", "锦江区"),
    Region("420102", "湖北省", "武汉市", "江岸区"),
    Region("610102", "陕西省", "西安市", "新城区"),
    Region("340102", "安徽省", "合肥市", "瑶海区"),
    Region("230102", "黑龙江省", "哈尔滨市", "道里区"),
    Region("210102", "辽宁省", "沈阳市", "和平区"),
    Region("350102", "福建省", "福州市", "鼓楼区"),
)

_CODE_INDEX: dict[str, Region] = {r.code: r for r in REGIONS}


def random_region() -> Region:
    return random.choice(REGIONS)


def region_by_code(code: str) -> Region | None:
    return _CODE_INDEX.get(code)


def region_by_code_prefix(code: str) -> Region | None:
    """Best-effort lookup: exact, then by 4-digit (city) / 2-digit (province)."""
    if code in _CODE_INDEX:
        return _CODE_INDEX[code]
    for length in (4, 2):
        prefix = code[:length]
        for region in REGIONS:
            if region.code.startswith(prefix):
                return region
    return None
