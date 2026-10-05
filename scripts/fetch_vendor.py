"""Fetch the browser libraries into static/vendor/ if they are missing.

The repo commits them, but a Space upload can skip the binaries (fonts) and
let the Docker build pull them from the npm registry instead.
"""
from __future__ import annotations

import io
import sys
import tarfile
import urllib.request
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "static" / "vendor"
PACKAGES = {
    # npm tarball -> {path inside tarball: destination under static/vendor}
    "https://registry.npmjs.org/marked/-/marked-12.0.2.tgz": {
        "package/marked.min.js": "marked.min.js",
        "package/LICENSE.md": "marked.LICENSE.md",
    },
    "https://registry.npmjs.org/dompurify/-/dompurify-3.1.6.tgz": {
        "package/dist/purify.min.js": "purify.min.js",
        "package/LICENSE": "dompurify.LICENSE",
    },
    "https://registry.npmjs.org/katex/-/katex-0.16.11.tgz": {
        "package/dist/katex.min.js": "katex/katex.min.js",
        "package/dist/katex.min.css": "katex/katex.min.css",
        "package/LICENSE": "katex/LICENSE",
        "package/dist/fonts/*.woff2": "katex/fonts/",
    },
}


def main() -> int:
    for url, files in PACKAGES.items():
        wanted = {dst for dst in files.values() if not dst.endswith("/")}
        globbed = [d for d in files.values() if d.endswith("/")]
        if all((VENDOR / d).exists() for d in wanted) and all(any((VENDOR / g).glob("*.woff2")) for g in globbed):
            continue
        print(f"fetching {url}")
        with urllib.request.urlopen(url, timeout=60) as r:
            tar = tarfile.open(fileobj=io.BytesIO(r.read()), mode="r:gz")
        for member in tar.getmembers():
            for src, dst in files.items():
                if src.endswith("*.woff2"):
                    prefix = src[: -len("*.woff2")]
                    if not (member.name.startswith(prefix) and member.name.endswith(".woff2")):
                        continue
                    target = VENDOR / dst / Path(member.name).name
                elif member.name == src:
                    target = VENDOR / dst
                else:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(member).read())
    return 0


if __name__ == "__main__":
    sys.exit(main())
