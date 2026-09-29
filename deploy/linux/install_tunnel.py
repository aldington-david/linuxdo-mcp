"""Build-time installation from a pinned official OpenAI release; never receives secrets."""
import hashlib
import io
from pathlib import Path
import sys
import urllib.request
import zipfile

HASHES = {
    "amd64": "8c836dc5d68d68b663d9a5c5b28ff9fa780d9f7a3fffb1c306880b8f32fab5f1",
    "arm64": "c51bfd883fc22e3445494a03c0179875176564bde470661b308fd83af5d01abb",
}
arch = sys.argv[1]
if arch not in HASHES:
    raise SystemExit("Tunnel image supports amd64 and arm64 only")
url = f"https://github.com/openai/tunnel-client/releases/download/v0.0.15/tunnel-client-v0.0.15-linux-{arch}.zip"
with urllib.request.urlopen(url, timeout=120) as response:
    payload = response.read()
if hashlib.sha256(payload).hexdigest() != HASHES[arch]:
    raise SystemExit("Official Tunnel archive checksum mismatch")
with zipfile.ZipFile(io.BytesIO(payload)) as archive:
    names = [name for name in archive.namelist() if Path(name).name == "tunnel-client"]
    if len(names) != 1:
        raise SystemExit("Unexpected archive contents")
    target = Path("/usr/local/bin/tunnel-client")
    target.write_bytes(archive.read(names[0]))
    target.chmod(0o755)
