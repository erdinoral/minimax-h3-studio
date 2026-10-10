"""Delete individual managed weight files, never arbitrary paths or directories."""
from pathlib import Path

FOLDERS=("diffusion_models", "unet", "text_encoders", "clip", "vae", "loras", "hyperflow", "refmods")
EXTENSIONS={".safetensors", ".gguf", ".sft", ".ckpt", ".pt", ".pth"}


def is_weight(path):
    return path.suffix.lower() in EXTENSIONS or (path.suffix.lower()=='.part' and path.with_suffix('').suffix.lower() in EXTENSIONS)


def target(root, folder, name):
    if folder not in FOLDERS or not name or Path(name).name != name or any(c in name for c in '/\\:'):
        raise ValueError("storage.invalidFile")
    path=Path(root)/folder/name
    if not is_weight(path) or path.is_symlink() or path.resolve().parent != (Path(root)/folder).resolve():
        raise ValueError("storage.invalidFile")
    return path


def inventory(root, protected=()):
    return [{"folder":folder,"file":p.name,"bytes":p.stat().st_size,"protected":p.name in protected}
            for folder in FOLDERS if (Path(root)/folder).is_dir()
            for p in sorted((Path(root)/folder).iterdir(),key=lambda p:p.name.lower())
            if p.is_file() and not p.is_symlink() and is_weight(p)]


def remove(root, folder, name, protected=()):
    path=target(root,folder,name)
    if name in protected:
        raise ValueError("storage.protected")
    if not path.is_file():
        raise FileNotFoundError("storage.notFound")
    size=path.stat().st_size
    path.unlink()
    return size
