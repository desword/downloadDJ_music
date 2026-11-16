#!/usr/bin/env python3
"""构建无需 macOS 构建工具的通用 .app 压缩包。"""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import stat
import struct
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]


def icon_png(size: int) -> bytes:
    """用标准库绘制黑胶唱片图标。"""
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            nx, ny = (x + .5) / size, (y + .5) / size
            # 深色背景、细唱片纹、珊瑚色中心和指针。
            radius = ((nx - .5) ** 2 + (ny - .52) ** 2) ** .5
            color = (20, 23, 34, 255)
            if radius < .41:
                color = (31, 35, 46, 255) if int(radius * 155) % 3 else (53, 57, 68, 255)
            if radius < .125:
                color = (255, 147, 109, 255)
            if radius < .018:
                color = (37, 31, 38, 255)
            if .72 < nx < .76 and .19 < ny < .56 and abs(nx - (.91 - ny * .35)) < .022:
                color = (226, 216, 205, 255)
            rows.extend(color)
    def chunk(name: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(rows), 9)) + chunk(b'IEND', b''))


def make_icon(path: Path) -> None:
    chunks = []
    for code, size in ((b'ic08', 256), (b'ic09', 512)):
        png = icon_png(size)
        chunks.append(code + struct.pack('>I', len(png) + 8) + png)
    payload = b''.join(chunks)
    path.write_bytes(b'icns' + struct.pack('>I', len(payload) + 8) + payload)


def build(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / 'DJ-Deck-macOS.zip'
    with tempfile.TemporaryDirectory(prefix='.dj-deck-build-', dir=output_dir) as tmp:
        app = Path(tmp) / 'DJ Deck.app'
        contents = app / 'Contents'
        resources = contents / 'Resources'
        executable = contents / 'MacOS' / 'DJ Deck'
        app_source = resources / 'app'
        executable.parent.mkdir(parents=True)
        app_source.mkdir(parents=True)
        plist = {
            'CFBundleName': 'DJ Deck', 'CFBundleDisplayName': 'DJ Deck',
            'CFBundleIdentifier': 'com.desword.djdeck', 'CFBundleVersion': '1',
            'CFBundleShortVersionString': '1.0', 'CFBundlePackageType': 'APPL',
            'CFBundleExecutable': 'DJ Deck', 'CFBundleIconFile': 'AppIcon',
            'NSHighResolutionCapable': True,
        }
        with (contents / 'Info.plist').open('wb') as f:
            plistlib.dump(plist, f)
        shutil.copyfile(ROOT / 'macos' / 'launcher.sh', executable)
        executable.chmod(0o755)
        for name in ('launch.command', 'check_dependencies.py'):
            dest = resources / name
            shutil.copyfile(ROOT / 'macos' / name, dest)
            dest.chmod(0o755 if name.endswith('.command') else 0o644)
        for directory in ('backend', 'frontend'):
            shutil.copytree(ROOT / directory, app_source / directory,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copyfile(ROOT / 'start.py', app_source / 'start.py')
        make_icon(resources / 'AppIcon.icns')
        temporary_archive = Path(tmp) / archive.name
        with zipfile.ZipFile(temporary_archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for path in sorted(app.rglob('*')):
                if not path.is_file():
                    continue
                info = zipfile.ZipInfo.from_file(path, arcname=str(path.relative_to(app.parent)))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                mode = 0o755 if path in (executable, resources / 'launch.command') else 0o644
                info.external_attr = (stat.S_IFREG | mode) << 16
                z.writestr(info, path.read_bytes())
        os.replace(temporary_archive, archive)
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='构建 DJ Deck macOS 应用压缩包')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    print(build(parser.parse_args().output_dir))
