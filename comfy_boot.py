"""
ComfyUI boot shim for Pinokio on Windows.

tqdm progress bars write \\r to stderr; under redirected/non-TTY stderr that
raises OSError [Errno 22] and kills sampling mid-job. Force-disable tqdm
before main.py loads. Studio already tracks progress via its own API.
"""
from __future__ import annotations

import runpy
import shutil
import sys
from pathlib import Path


def _disable_tqdm() -> None:
    try:
        import tqdm.std as tqdm_std

        _orig_init = tqdm_std.tqdm.__init__

        def _init(self, *args, **kwargs):
            kwargs["disable"] = True
            return _orig_init(self, *args, **kwargs)

        tqdm_std.tqdm.__init__ = _init  # type: ignore[method-assign]
    except Exception:
        pass


def main() -> None:
    app_dir = Path(__file__).resolve().parent / "app"
    # Ship our own small control node with Studio; no external node/core patch.
    source = app_dir.parent / 'studio' / 'comfy_nodes' / 'h3_studio_render_control'
    destination = app_dir / 'custom_nodes' / 'h3_studio_render_control'
    destination.mkdir(parents=True, exist_ok=True)
    for module in source.glob('*.py'):
        shutil.copy2(module, destination / module.name)
    sys.path.insert(0, str(app_dir))
    sys.argv[0] = str(app_dir / "main.py")
    _disable_tqdm()
    runpy.run_path(str(app_dir / "main.py"), run_name="__main__")


if __name__ == "__main__":
    main()
