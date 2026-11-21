"""Shared file hashing and atomic JSON writes."""
from pathlib import Path
import hashlib
import json


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    # Write beside the destination so replacement is atomic on the same filesystem.
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import os,tempfile
    content=json.dumps(value,indent=2,allow_nan=False)+'\n'
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix='.'+path.name+'.',delete=False) as stream:
            temporary=Path(stream.name);stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None and temporary.exists():temporary.unlink()
