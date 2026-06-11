import re
from pypinyin import lazy_pinyin


def to_pinyin_initials(text: str) -> str:
    """将中文文本转换为拼音首字母，英文/数字保持不变

    Args:
        text: 输入的字符串

    Returns:
        拼音首字母组成的字符串，如 "name测试" -> "namecs"
    """
    if not text:
        return ""

    # 判断是否包含中文
    if re.search(r'[一-鿿]', text):
        # Check if it's a common name-like pattern (e.g., '姓名', '名字')
        if text in ['姓名', '名字', '手机号', '电话', '邮箱']:
            # Preserve the original text for common name-like columns
            result = text
        else:
            # For other Chinese text, use pinyin initials
            pinyin_list = lazy_pinyin(text)
            # Take first letter of each pinyin
            initials = [p[0] if p else '' for p in pinyin_list]
            result = ''.join(initials)
    else:
        # No Chinese characters, keep original
        result = text

    # 清理特殊字符，只保留字母、数字和下划线，并转为小写
    result = re.sub(r'[^a-zA-Z0-9_]', '', result).lower()
    return result if result else "col"


def filename_to_table_name(text: str) -> str:
    """从文件名生成表名：先去除所有非中文字符，再取剩余中文的拼音首字母。

    Args:
        text: 输入的文件名（不含扩展名）

    Returns:
        所有中文拼音首字母组成的小写字符串，如 "2023年-销售report.csv" -> "nsl"。
        若不含任何中文字符，则返回空字符串（由调用方回退为 "auto_table"）。
    """
    if not text:
        return ""

    # 仅保留中文字符，去除字母、数字、符号、空格等所有非中文
    chinese_only = re.sub(r'[^\u4e00-\u9fff]', '', text)
    if not chinese_only:
        return ""

    # 取每个中文字拼音的首字母
    pinyin_list = lazy_pinyin(chinese_only)
    initials = [p[0] for p in pinyin_list if p]
    return ''.join(initials).lower()
