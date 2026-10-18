"""Extract the release to a different Unicode path and verify the EXE again."""
from pathlib import Path
import subprocess
import sys
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    archive = root / "release/MediaForge-0.1.0-windows-x64-portable.zip"
    extracted = root / "artifacts/便携包 解压验收"
    if extracted.exists():
        raise SystemExit("Extraction verification directory already exists; move it aside first.")
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None, "Archive CRC verification failed"
        for name in bundle.namelist():
            target = (extracted / name).resolve()
            assert target.is_relative_to(extracted.resolve()), "Unsafe archive path"
        assert "MediaForge/MediaForge.exe" in bundle.namelist()
        assert not any(name.lower().endswith((".vbs", ".msi")) for name in bundle.namelist())
        bundle.extractall(extracted)
    subprocess.run([sys.executable, str(root / "scripts/verify_package.py"), "--portable",
                    "--executable", str(extracted / "MediaForge/MediaForge.exe"),
                    "--area", str(root / "artifacts/portable-extracted-check")], cwd=root, check=True)
    print("ZIP integrity, Unicode relocation, direct EXE startup and 6 real conversions passed.")


if __name__ == "__main__":
    main()
