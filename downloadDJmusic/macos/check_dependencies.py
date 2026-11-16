"""验证应用锁定的直接依赖及其传递依赖。"""
import importlib
import importlib.metadata
from pathlib import Path
import re
import subprocess
import sys

try:
    for line in Path(sys.argv[1]).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([^\s]+)', line)
        if not match:
            raise ValueError('无法检查依赖：' + line)
        name, version = match.groups()
        if importlib.metadata.version(name) != version:
            raise ValueError(name + ' 的版本不匹配')
        importlib.import_module(name.replace('-', '_'))
    subprocess.run([sys.executable, '-m', 'pip', 'check'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
except (ValueError, ImportError, OSError, subprocess.CalledProcessError) as exc:
    print(f'需要安装依赖：{exc}', file=sys.stderr)
    sys.exit(1)
