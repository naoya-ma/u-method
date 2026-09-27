import re

# ✅ パラメータ入力欄の記法は二重波カッコ {{param}} を使う（単一波カッコ {param} だと、
# PowerShell/バッチスクリプトのスクリプトブロック構文（例: `Where-Object {$_.Id -in 3076,3077}`）を
# 誤ってパラメータ名と認識してしまうため。ツールのバッチ/PowerShellスクリプト対応を追加した際に
# ジョブ側も含めて統一した
_PARAM_PATTERN = re.compile(r"\{\{(.*?)\}\}")


def extract_params(command: str):
    """
    {{param}} を抽出してリストで返す
    """
    return _PARAM_PATTERN.findall(command)


def substitute_params(command: str, values: dict) -> str:
    """
    {{param}} をvaluesの値で置換する。str.format()は使わない
    （二重波カッコはPythonのformatでは`{{`/`}}`がリテラルの単一波カッコとして扱われ意図通り
    置換されない上、単一波カッコを含む本文〈PowerShellスクリプト等〉を.format()に通すと
    KeyError/ValueErrorを誘発するため、単純な文字列置換にする）
    """
    result = command
    for name, value in values.items():
        result = result.replace("{{" + name + "}}", value)
    return result
