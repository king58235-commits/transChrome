"""Build release/transChrome-<VERSION>.zip from the repository source.

Takes the files Git tracks plus new, not-ignored files (so venv, runtime,
models, logs, recordings and anything else in .gitignore are never included),
minus Git's own dotfiles. Batch files are written with CRLF line endings,
which cmd.exe needs; everything else is stored as is.

From the project root:
    backend\\venv\\Scripts\\python.exe backend\\make_release.py
"""
import os
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import VERSION  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {".gitignore", ".gitattributes"}


def source_files():
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                         cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8")
    return sorted(p for p in out.split("\0") if p and p not in SKIP and os.path.isfile(os.path.join(ROOT, p)))


def main():
    name = f"transChrome-{VERSION}"
    os.makedirs(os.path.join(ROOT, "release"), exist_ok=True)
    zip_path = os.path.join(ROOT, "release", f"{name}.zip")
    files = source_files()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            data = open(os.path.join(ROOT, rel), "rb").read()
            if rel.lower().endswith(".bat"):
                data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            zf.writestr(f"{name}/{rel}", data)
    print(f"{zip_path}: {len(files)} files, {os.path.getsize(zip_path) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
