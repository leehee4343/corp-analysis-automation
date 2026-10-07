"""공문 PPTX -> 세로로 긴 PNG 한 장 (영업 관리 '이미지 다운로드').

PPTX를 PDF로 바꾼 뒤(PowerPoint 또는 LibreOffice) PyMuPDF로 쪽마다 그려 위에서 아래로 잇는다.
변환기는 실행 환경에 따라 고른다:
- Windows에 PowerPoint가 설치돼 있으면 PowerPoint (샘플과 똑같이 나옴, 로컬 실행판)
- 그 밖에는 LibreOffice(soffice). Render(Linux) 서버는 Dockerfile에서 LibreOffice와 나눔고딕을 설치하고,
  템플릿 글꼴인 맑은 고딕(배포 불가)을 나눔고딕으로 대체한다(fonts-malgun-alias.conf). 글자 폭이 달라 줄바꿈이
  PowerPoint와 조금 다를 수 있다.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

IMAGE_WIDTH = 1600   # px. A4 세로 한 쪽 ≈ 1600x2260 (휴대폰에서 확대해도 글자가 선명한 정도)
PAGE_GAP = 24        # 쪽 사이 간격(px)
GAP_COLOR = (229, 231, 235)
BATCH = 20           # 변환기 한 번 실행에 넘기는 파일 수 (메모리·시간 제한)

_lock = threading.Lock()  # PowerPoint·LibreOffice는 동시에 여러 변환을 돌리면 충돌한다

# PowerPoint로 LETTER_DIR의 in_0.pptx … in_{N-1}.pptx를 같은 이름의 PDF로 저장한다.
# 사용자가 PowerPoint를 열어 두었으면 끄지 않는다(열린 프레젠테이션이 있으면 Quit 안 함).
_PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$dir = $env:LETTER_DIR; $n = [int]$env:LETTER_COUNT
$app = New-Object -ComObject PowerPoint.Application
$had = $app.Presentations.Count
try {
  for ($i = 0; $i -lt $n; $i++) {
    $p = $app.Presentations.Open("$dir\in_$i.pptx", $true, $false, $false)
    try { $p.SaveAs("$dir\in_$i.pdf", 32) } finally { $p.Close() }
  }
} finally {
  if ($had -eq 0 -and $app.Presentations.Count -eq 0) { $app.Quit() }
}
"""

_SOFFICE_CANDIDATES = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]


class ImageConversionError(RuntimeError):
    pass


def _has_powerpoint() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"PowerPoint.Application\CurVer"))
        return True
    except OSError:
        return False


def _soffice() -> str | None:
    found = shutil.which("soffice") or shutil.which("libreoffice")
    return found or next((p for p in _SOFFICE_CANDIDATES if Path(p).exists()), None)


def find_converter() -> tuple[str, str | None] | None:
    """('powerpoint', None) 또는 ('libreoffice', soffice 경로). 둘 다 없으면 None."""
    if _has_powerpoint():
        return "powerpoint", None
    soffice = _soffice()
    return ("libreoffice", soffice) if soffice else None


def _convert_dir(converter: tuple[str, str | None], workdir: Path, count: int) -> None:
    kind, soffice = converter
    timeout = 60 + 15 * count
    if kind == "powerpoint":
        env = {**os.environ, "LETTER_DIR": str(workdir), "LETTER_COUNT": str(count)}
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _PS_SCRIPT]
    else:
        env = dict(os.environ)
        profile = (Path(tempfile.gettempdir()) / "letter-soffice-profile").as_uri()  # 첫 실행 후 재사용
        cmd = [soffice, "--headless", "--norestore", "--nolockcheck", f"-env:UserInstallation={profile}",
               "--convert-to", "pdf", "--outdir", str(workdir)] + [str(workdir / f"in_{i}.pptx") for i in range(count)]
    try:
        res = subprocess.run(cmd, env=env, capture_output=True, timeout=timeout,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as e:
        raise ImageConversionError("공문을 이미지로 바꾸는 데 시간이 너무 오래 걸립니다. 기업 수를 줄여 다시 시도하세요.") from e
    if res.returncode != 0:
        err = (res.stderr or res.stdout or b"").decode("utf-8", "replace").strip()[-300:]
        raise ImageConversionError(f"공문을 PDF로 바꾸지 못했습니다({kind}). {err}")


def pptx_to_pdfs(pptx_files: list[bytes]) -> list[bytes]:
    converter = find_converter()
    if converter is None:
        raise ImageConversionError("이미지로 바꿀 프로그램이 없습니다. PowerPoint 또는 LibreOffice를 설치하세요.")
    out: list[bytes] = []
    with _lock:
        for start in range(0, len(pptx_files), BATCH):
            chunk = pptx_files[start:start + BATCH]
            with tempfile.TemporaryDirectory(prefix="letter-") as tmp:
                workdir = Path(tmp)
                for i, content in enumerate(chunk):
                    (workdir / f"in_{i}.pptx").write_bytes(content)
                _convert_dir(converter, workdir, len(chunk))
                for i in range(len(chunk)):
                    pdf = workdir / f"in_{i}.pdf"
                    if not pdf.exists():
                        raise ImageConversionError("공문 PDF가 만들어지지 않았습니다.")
                    out.append(pdf.read_bytes())
    return out


def pdf_to_long_png(pdf: bytes, width: int = IMAGE_WIDTH, gap: int = PAGE_GAP) -> bytes:
    """PDF의 모든 쪽을 같은 폭으로 그려 세로로 잇는다(쪽 사이에 옅은 회색 간격)."""
    pages = []
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        for page in doc:
            zoom = width / page.rect.width
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            pages.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    if not pages:
        raise ImageConversionError("공문 PDF에 쪽이 없습니다.")
    w = max(p.width for p in pages)
    canvas = Image.new("RGB", (w, sum(p.height for p in pages) + gap * (len(pages) - 1)), GAP_COLOR)
    y = 0
    for p in pages:
        canvas.paste(p, (0, y))
        y += p.height + gap
    buf = io.BytesIO()
    canvas.save(buf, "PNG", compress_level=6)
    return buf.getvalue()


def pptx_to_long_pngs(pptx_files: list[bytes]) -> list[bytes]:
    return [pdf_to_long_png(pdf) for pdf in pptx_to_pdfs(pptx_files)]
