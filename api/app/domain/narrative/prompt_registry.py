"""Versioned prompt loading + integrity verification (blueprint §13.4).

Prompts are files on disk, not strings in code, specifically so they can
be reviewed and diffed like any other regulated artifact. `registry.json`
records the SHA-256 of every prompt file at the moment a version was
activated; `PromptRegistry` recomputes those hashes from the files
actually on disk right now and refuses to load on any mismatch. Without
this, editing a prompt in place could silently change model behavior in a
system whose whole design premise is end-to-end auditability — exactly
the "unvalidated model input" SR 11-7 concern §13.4 names.
"""

import hashlib
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_PROMPTS_ROOT = Path(__file__).parent / "prompts"
_REGISTRY_PATH = _PROMPTS_ROOT / "registry.json"


class PromptIntegrityError(RuntimeError):
    pass


class PromptRegistry:
    def __init__(self, version: str):
        self.version = version
        self.version_dir = _PROMPTS_ROOT / version
        if not self.version_dir.is_dir():
            raise PromptIntegrityError(f"no prompt directory for version {version!r} at {self.version_dir}")

        registry = json.loads(_REGISTRY_PATH.read_text())
        entry = registry.get(version)
        if entry is None:
            raise PromptIntegrityError(f"version {version!r} is not recorded in {_REGISTRY_PATH}")

        for filename, expected_hash in entry["files"].items():
            path = self.version_dir / filename
            if not path.exists():
                raise PromptIntegrityError(f"registry lists {filename} for {version!r} but it is missing on disk")
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                raise PromptIntegrityError(
                    f"prompt file {filename} (version {version!r}) has changed since it was activated: "
                    f"registry hash {expected_hash}, actual hash {actual_hash}. "
                    "Bump the version and add a new registry.json entry rather than editing an activated prompt in place."
                )

        self._env = Environment(loader=FileSystemLoader(str(self.version_dir)), undefined=StrictUndefined)
        self._system_text = (self.version_dir / "system.txt").read_text()

    def system(self) -> str:
        return self._system_text

    def render(self, section_id: str, **context) -> str:
        template = self._env.get_template(f"section_{section_id}.txt")
        return template.render(**context)
