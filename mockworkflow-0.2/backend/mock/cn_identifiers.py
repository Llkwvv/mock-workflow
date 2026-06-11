"""Chinese domain identifier generators with real checksum algorithms.

These produce *format-valid* fabricated identifiers (passing their official
check-digit algorithms) without reusing any real sample value:

  - 居民身份证号 (GB 11643-1999, 18-digit, ISO 7064 MOD 11-2 check)
  - 统一社会信用代码 (GB 32100-2015, 18-char, ISO 7064 MOD 31-3 check)
  - 银行卡号 (Luhn / MOD 10 check)
  - 车牌号 / 邮政编码

The ID-card generator also exposes the *encoded* facts (birthdate, gender,
region) so the cross-field coherence pass can keep 出生日期 / 性别 / 年龄 / 籍贯
consistent with the generated number.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime

from backend.mock.region_data import Region, random_region, region_by_code_prefix


# --------------------------------------------------------------------------- #
# 居民身份证号
# --------------------------------------------------------------------------- #

_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK_MAP = "10X98765432"


@dataclass(frozen=True)
class IdentityInfo:
    id_card: str
    birthdate: date
    gender: str          # "男" / "女"
    region: Region


def _id_check_digit(first17: str) -> str:
    total = sum(int(ch) * w for ch, w in zip(first17, _ID_WEIGHTS))
    return _ID_CHECK_MAP[total % 11]


def generate_id_card(
    birthdate: date | None = None,
    gender: str | None = None,
    region: Region | None = None,
) -> IdentityInfo:
    """Generate a checksum-valid 18-digit resident ID card and its facts."""
    region = region or random_region()
    if birthdate is None:
        start = date(1950, 1, 1).toordinal()
        end = date(2006, 12, 31).toordinal()
        birthdate = date.fromordinal(random.randint(start, end))

    # 17th digit parity encodes gender (odd=male, even=female).
    if gender in ("男", "M", "m", "1", 1, True):
        seq_last = random.choice((1, 3, 5, 7, 9))
        gender_label = "男"
    elif gender in ("女", "F", "f", "0", "2", 0, 2, False):
        seq_last = random.choice((0, 2, 4, 6, 8))
        gender_label = "女"
    else:
        seq_last = random.randint(0, 9)
        gender_label = "男" if seq_last % 2 == 1 else "女"

    seq = f"{random.randint(0, 99):02d}{seq_last}"
    first17 = f"{region.code}{birthdate.strftime('%Y%m%d')}{seq}"
    full = first17 + _id_check_digit(first17)
    return IdentityInfo(id_card=full, birthdate=birthdate, gender=gender_label, region=region)


def validate_id_card(value: str) -> bool:
    value = value.strip().upper()
    if len(value) != 18 or not value[:17].isdigit():
        return False
    return _id_check_digit(value[:17]) == value[17]


def parse_id_card(value: str) -> IdentityInfo | None:
    """Decode region / birthdate / gender from a valid 18-digit ID card."""
    if not validate_id_card(value):
        return None
    value = value.strip().upper()
    try:
        birthdate = datetime.strptime(value[6:14], "%Y%m%d").date()
    except ValueError:
        return None
    gender = "男" if int(value[16]) % 2 == 1 else "女"
    region = region_by_code_prefix(value[:6]) or random_region()
    return IdentityInfo(id_card=value, birthdate=birthdate, gender=gender, region=region)


# --------------------------------------------------------------------------- #
# 统一社会信用代码 (18-char)
# --------------------------------------------------------------------------- #

_USCC_CHARS = "0123456789ABCDEFGHJKLMNPQRTUWXY"   # 31-char set (excludes I,O,S,V,Z)
_USCC_CHAR_INDEX = {c: i for i, c in enumerate(_USCC_CHARS)}
_USCC_WEIGHTS = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)

# 登记管理部门代码 + 机构类别代码 (常见组合)
_USCC_PREFIXES = ("91", "92", "93", "11", "12", "51", "52", "53")


def _uscc_check_char(first17: str) -> str:
    total = sum(_USCC_CHAR_INDEX[c] * w for c, w in zip(first17, _USCC_WEIGHTS))
    check = (31 - (total % 31)) % 31
    return _USCC_CHARS[check]


def generate_credit_code(region: Region | None = None) -> str:
    """Generate a checksum-valid 18-char 统一社会信用代码."""
    region = region or random_region()
    prefix = random.choice(_USCC_PREFIXES)               # 2 chars
    org_code = "".join(random.choice(_USCC_CHARS) for _ in range(9))  # 主体标识码
    first17 = f"{prefix}{region.code}{org_code}"
    return first17 + _uscc_check_char(first17)


def validate_credit_code(value: str) -> bool:
    value = value.strip().upper()
    if len(value) != 18 or any(c not in _USCC_CHAR_INDEX for c in value):
        return False
    return _uscc_check_char(value[:17]) == value[17]


# --------------------------------------------------------------------------- #
# 银行卡号 (Luhn)
# --------------------------------------------------------------------------- #

# Common mainland-bank BIN prefixes (debit cards).
_BANK_BINS = ("621700", "622202", "621226", "622848", "622588", "621661", "622908")


def _luhn_check_digit(number_without_check: str) -> str:
    digits = [int(d) for d in number_without_check]
    digits.reverse()
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 0:          # positions that get doubled (from the right, 0-indexed)
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def generate_bank_card(length: int = 19) -> str:
    """Generate a Luhn-valid bank card number (default 19 digits)."""
    bin_prefix = random.choice(_BANK_BINS)
    body_len = max(length - len(bin_prefix) - 1, 1)
    body = "".join(str(random.randint(0, 9)) for _ in range(body_len))
    partial = bin_prefix + body
    return partial + _luhn_check_digit(partial)


def validate_bank_card(value: str) -> bool:
    value = value.strip()
    if not value.isdigit() or len(value) < 12:
        return False
    return _luhn_check_digit(value[:-1]) == value[-1]


# --------------------------------------------------------------------------- #
# 车牌号 / 邮政编码
# --------------------------------------------------------------------------- #

_PLATE_PROVINCES = "京津冀晋蒙辽吉黑沪苏浙皖闽赣鲁豫鄂湘粤桂琼渝川贵云陕甘青"
_PLATE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"   # excludes I, O


def generate_plate() -> str:
    province = random.choice(_PLATE_PROVINCES)
    city = random.choice(_PLATE_LETTERS)
    body = "".join(random.choice(_PLATE_LETTERS + "0123456789") for _ in range(5))
    return f"{province}{city}{body}"


def generate_postal_code(region: Region | None = None) -> str:
    """6-digit postal code; first two digits loosely follow the province code."""
    region = region or random_region()
    head = region.code[:2]
    return head + "".join(str(random.randint(0, 9)) for _ in range(4))
