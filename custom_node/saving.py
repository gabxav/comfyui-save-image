"""Image encoding and collision-safe writes, independent of ComfyUI."""

import json
import os
import re
import tempfile
from pathlib import Path

from PIL import Image, PngImagePlugin


def destination(root, folder, prefix):
    root = Path(root).resolve()
    if not isinstance(prefix, str) or not prefix.strip():
        raise ValueError("filename_prefix must not be empty.")
    if prefix in (".", "..") or re.search(r'[<>:"/\\|?*\x00-\x1f]', prefix):
        raise ValueError("filename_prefix must be a filename, without folder separators.")
    if prefix.endswith((" ", ".")):
        raise ValueError("filename_prefix must not end in a space or dot.")
    folder = folder.strip()
    if Path(folder).is_absolute() or "\\" in folder or ":" in folder:
        raise ValueError("output_folder must be relative to the ComfyUI output directory.")
    if ".." in Path(folder).parts:
        raise ValueError("output_folder must not contain '..'.")
    target = (root / folder).resolve()
    if not target.is_relative_to(root):
        raise ValueError("output_folder resolves outside the ComfyUI output directory.")
    target.mkdir(parents=True, exist_ok=True)
    return target, "" if target == root else target.relative_to(root).as_posix()


def reserve(target, prefix, extension, sidecar):
    # Scan once, then use exclusive creation to arbitrate concurrent executions.
    pattern = re.compile(re.escape(prefix) + r"_(\d+)\.(?:png|jpg|json)$")
    counter = 1
    for entry in target.iterdir():
        match = pattern.fullmatch(entry.name)
        if match:
            counter = max(counter, int(match[1]) + 1)
    while True:
        path = target / f"{prefix}_{counter:05d}.{extension}"
        owned = []
        try:
            for candidate in ([path, path.with_suffix(".json")] if sidecar else [path]):
                fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
                os.close(fd)
                owned.append(candidate)
            return path, owned
        except FileExistsError:
            for candidate in owned:
                candidate.unlink()
            counter += 1
        except BaseException:
            for candidate in owned:
                candidate.unlink(missing_ok=True)
            raise


def atomic_write(path, writer):
    fd, name = tempfile.mkstemp(prefix=".xavier-save-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def save_image(image, target, prefix, image_format, png_compression, jpeg_quality, metadata):
    sidecar = image_format == "JPEG" and metadata is not None
    path, owned = reserve(target, prefix, "png" if image_format == "PNG" else "jpg", sidecar)
    try:
        if image_format == "PNG":
            pnginfo = PngImagePlugin.PngInfo()
            for key, value in (metadata or {}).items():
                pnginfo.add_text(key, json.dumps(value, ensure_ascii=False))
            atomic_write(path, lambda stream: image.save(
                stream, format="PNG", compress_level=png_compression, pnginfo=pnginfo))
        else:
            if image.mode == "RGBA":
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            atomic_write(path, lambda stream: image.save(
                stream, format="JPEG", quality=jpeg_quality, optimize=True, subsampling=0))
            if sidecar:
                payload = json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")
                atomic_write(path.with_suffix(".json"), lambda stream: stream.write(payload))
    except BaseException:
        for candidate in owned:
            candidate.unlink(missing_ok=True)
        raise
    return path
