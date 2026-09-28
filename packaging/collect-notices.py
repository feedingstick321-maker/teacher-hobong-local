"""Collect installed runtime notices without copying source documents or secrets."""
import argparse
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.request import urlopen

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--corresponding-source-url", help="Public URL for the matching AGPL source release")
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
args.output.mkdir(parents=True, exist_ok=True)
runtime = ["pymupdf", "rapidocr", "rapidfuzz", "onnxruntime", "opencv-python", "numpy", "pillow",
           "xlsxwriter", "reportlab", "requests", "urllib3", "idna", "certifi", "charset-normalizer",
           "omegaconf", "antlr4-python3-runtime", "pyyaml", "pyclipper", "shapely", "six", "tqdm",
           "colorlog", "coloredlogs", "humanfriendly", "flatbuffers", "packaging", "protobuf", "sympy",
           "mpmath", "colorama", "typing-extensions", "pyreadline3", "pyinstaller"]
upstream_notices = {
    ("rapidocr", "3.9.1"): "https://raw.githubusercontent.com/RapidAI/RapidOCR/v3.9.1/LICENSE",
    ("antlr4-python3-runtime", "4.9.3"): "https://raw.githubusercontent.com/antlr/antlr4/4.9.3/LICENSE.txt",
    ("flatbuffers", "25.12.19"): "https://raw.githubusercontent.com/google/flatbuffers/v25.12.19/LICENSE",
}

def upstream_copy(url, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with urlopen(url, timeout=30) as response:
            content = response.read()
        if len(content) < 500 or b"<html" in content.lower():
            raise ValueError(f"Invalid upstream license response: {url}")
        target.write_bytes(content)
    return {"url": url, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
report = {"python": [], "rust": [], "corresponding_source_url": args.corresponding_source_url,
          "release_blockers": []}
if not args.corresponding_source_url:
    report["release_blockers"].append(
        "PyMuPDF: publish the matching AGPL source and pass --corresponding-source-url.")

for name in runtime:
    dist = distribution(name)
    target = args.output / "python" / f"{name}-{dist.version}"
    copied = []
    for file in dist.files or []:
        if not re.search(r"license|copying|copyright|notice", str(file), re.I):
            continue
        source = Path(dist.locate_file(file))
        if not source.is_file() or source.suffix in (".py", ".pyc", ".pyd", ".dll"):
            continue
        target.mkdir(parents=True, exist_ok=True)
        dest = target / f"{len(copied):02d}-{source.name}"
        shutil.copyfile(source, dest)
        copied.append(str(dest.relative_to(args.output)))
    upstream = None
    if not copied and (name, dist.version) in upstream_notices:
        dest = target / "00-UPSTREAM-LICENSE.txt"
        upstream = upstream_copy(upstream_notices[(name, dist.version)], dest)
        copied.append(str(dest.relative_to(args.output)))
    if not copied:
        report["release_blockers"].append(f"No license file collected: {name} {dist.version}")
    report["python"].append({"name": name, "version": dist.version,
        "license": dist.metadata.get("License-Expression") or dist.metadata.get("License"), "files": copied, "upstream": upstream})

python_license = Path(sys.base_prefix) / "LICENSE.txt"
shutil.copyfile(python_license, args.output / "CPython-LICENSE.txt")
report["cpython"] = {"version": sys.version, "file": "CPython-LICENSE.txt"}
report["ocr_model_license"] = upstream_copy(
    "https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/v3.0.0/LICENSE",
    args.output / "PaddleOCR-APACHE-2.0.txt")

run = subprocess.run(["cargo", "metadata", "--offline", "--locked", "--format-version", "1",
                      "--filter-platform", "x86_64-pc-windows-msvc",
                      "--manifest-path", str(root / "desktop/src-tauri/Cargo.toml")],
                     capture_output=True, text=True, encoding="utf-8", check=True)
metadata = json.loads(run.stdout)
for package in metadata["packages"]:
    if not package.get("source"):
        continue
    source = Path(package["manifest_path"]).parent
    target = args.output / "rust" / f"{package['name']}-{package['version']}"
    copied = []
    for file in source.iterdir():
        if file.is_file() and re.search(r"^(license|copying|copyright|notice)", file.name, re.I):
            target.mkdir(parents=True, exist_ok=True)
            dest = target / file.name
            shutil.copyfile(file, dest)
            copied.append(str(dest.relative_to(args.output)))
    report["rust"].append({"name": package["name"], "version": package["version"],
                          "license": package.get("license"), "repository": package.get("repository"), "files": copied})
(args.output / "component-inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"python_packages": len(report["python"]), "rust_lock_packages": len(report["rust"]),
                  "release_blockers": report["release_blockers"]}))
