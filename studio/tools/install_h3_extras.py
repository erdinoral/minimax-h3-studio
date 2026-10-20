"""Install optional, pinned H3 decoding and colour tools without selecting them."""
import hashlib
import json
import shutil
import subprocess
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'app'
REVISION = '137541ff66fbe22d35beb73e09bca5d663b70cc5'
WEIGHTS = {
    'minimax_h3_lightvae_lite_vae_int8_convrot.safetensors':
        (1036943392, 'd9bde765b71ac35ee6531a32546c7ad2d50b89e5a812e1b0962b20add1ee6867'),
}
PACK = 'ComfyUI-H3-ClipColorAnchor'
PACK_REVISION = 'f3ab876bef12bc717cfd627123183f7864662b1a'


def require_stopped():
    url = os.environ.get('COMFY_URL', 'http://127.0.0.1:8188').rstrip('/')
    try:
        urllib.request.urlopen(url + '/system_stats', timeout=2).close()
    except urllib.error.HTTPError:
        pass  # An HTTP response still proves a server is running.
    except urllib.error.URLError:
        return
    raise RuntimeError('Finish the queue and stop Studio in Pinokio before installing Optional Film Tools. No render was cancelled.')


def verify(path, size, sha):
    if not path.is_file() or path.stat().st_size != size:
        return False
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest() == sha


def main():
    source = APP / 'comfy' / 'ldm' / 'minimax' / 'vae.py'
    if 'encoder_kept_blocks' not in source.read_text(encoding='utf-8'):
        raise RuntimeError('LightVAE needs ComfyUI 0.41.0 or later. Finish the queue, stop Studio, update ComfyUI, then retry Optional Film Tools.')
    target = APP / 'custom_nodes' / PACK
    if not target.exists():
        subprocess.run(['git', 'clone', '--no-checkout',
            'https://github.com/lovemachine100/' + PACK + '.git', str(target)], check=True)
        subprocess.run(['git', '-C', str(target), 'checkout', '--detach', PACK_REVISION], check=True)
    elif not (target / '__init__.py').is_file():
        raise RuntimeError('Incomplete ColorAnchor installation; existing folder was preserved')
    from huggingface_hub import hf_hub_download
    folder = APP / 'models' / 'vae'
    folder.mkdir(parents=True, exist_ok=True)
    for name, (size, sha) in WEIGHTS.items():
        destination = folder / name
        if destination.exists():
            if not verify(destination, size, sha):
                raise RuntimeError('Existing weight failed checksum; preserved: ' + name)
            continue
        if shutil.disk_usage(folder).free < size * 2 + 1024**3:
            raise RuntimeError('Insufficient space for verified LightVAE installation')
        downloaded = Path(hf_hub_download('Kijai/MiniMax-H3-experimental', name,
            revision=REVISION, local_dir=str(folder / '.h3-extras-download')))
        if not verify(downloaded, size, sha):
            raise RuntimeError('LightVAE checksum mismatch; file was not activated')
        downloaded.replace(destination)
        print('Verified LightVAE:', name, flush=True)
    dest = APP / 'user' / 'default' / 'workflows'
    dest.mkdir(parents=True, exist_ok=True)
    for path in (target / 'example_workflows').glob('*.json'):
        # Colour workflows keep the author's input/mask placeholders. Never
        # rewrite them into a generator or inject them into native Continuum.
        json.loads(path.read_text(encoding='utf-8-sig'))
        output = dest / ('H3 Studio Color Anchor - ' + path.name)
        if not output.exists():
            shutil.copy2(path, output)
    print('Optional H3 tools installed. Restart ComfyUI to register ColorAnchor. '
          'Select LightVAE under Settings > Advanced H3 models > Video decoder. '
          'Existing model selections were not changed.', flush=True)


if __name__ == '__main__':
    if '--check-stopped' in sys.argv:
        require_stopped()
    else:
        main()
