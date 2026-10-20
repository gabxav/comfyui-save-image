import numpy as np
from PIL import Image

import folder_paths
from comfy.cli_args import args

from .saving import destination, save_image


class XavierSaveImage:
    CATEGORY = "xavierlab/image"
    FUNCTION = "save"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("file_paths",)
    OUTPUT_IS_LIST = (True,)
    SEARCH_ALIASES = ["xavierlab", "save image", "png", "jpeg", "compression"]
    DESCRIPTION = (
        "Save an IMAGE batch as PNG or JPEG, with compression, prefix and output subfolder. "
        "PNG preserves alpha; JPEG composites alpha on white. Files are never overwritten. "
        "Returns one absolute server path per image and previews the saved files."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "format": (["PNG", "JPEG"], {"default": "PNG"}),
                "filename_prefix": ("STRING", {"default": "ComfyUI",
                    "tooltip": "Filename prefix only. Use output_folder for subfolders."}),
                "output_folder": ("STRING", {"default": "",
                    "tooltip": "Subfolder of the server's ComfyUI output directory. Empty uses its root."}),
                "png_compression": ("INT", {"default": 6, "min": 0, "max": 9,
                    "tooltip": "PNG only. 0: no compression; 9: strongest compression. Lossless."}),
                "jpeg_quality": ("INT", {"default": 90, "min": 1, "max": 100,
                    "tooltip": "JPEG only. Lower values reduce size and quality. Above 95 is usually unnecessary."}),
                "save_metadata": ("BOOLEAN", {"default": True,
                    "tooltip": "Embed prompt/workflow in PNG, or save a companion JSON for JPEG. Respects --disable-metadata."}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    def save(self, images, format="PNG", filename_prefix="ComfyUI", output_folder="",
             png_compression=6, jpeg_quality=90, save_metadata=True,
             prompt=None, extra_pnginfo=None):
        if format not in ("PNG", "JPEG"):
            raise ValueError("format must be PNG or JPEG.")
        if not 0 <= png_compression <= 9 or not 1 <= jpeg_quality <= 100:
            raise ValueError("Invalid PNG compression or JPEG quality.")
        if images.ndim != 4 or images.shape[-1] not in (1, 3, 4):
            raise ValueError("Expected IMAGE shaped [batch, height, width, 1/3/4].")
        if min(images.shape[:3]) < 1:
            raise ValueError("IMAGE batch and dimensions must be non-empty.")
        target, subfolder = destination(folder_paths.get_output_directory(), output_folder, filename_prefix)
        metadata = None
        if save_metadata and not args.disable_metadata:
            metadata = dict(extra_pnginfo or {})
            if prompt is not None:
                metadata["prompt"] = prompt
        paths, previews = [], []
        for frame in images:
            # Copy before sanitizing: never mutate the upstream tensor or transfer the whole batch.
            pixels = frame.detach().cpu().float().numpy()
            pixels = np.nan_to_num(pixels, copy=True, nan=0, posinf=1, neginf=0)
            pixels = (np.clip(pixels, 0, 1) * 255).astype(np.uint8)
            if pixels.shape[-1] == 1:
                pixels = pixels[..., 0]
            path = save_image(Image.fromarray(pixels), target, filename_prefix,
                              format, png_compression, jpeg_quality, metadata)
            paths.append(str(path))
            previews.append({"filename": path.name, "subfolder": subfolder, "type": "output"})
        return {"ui": {"images": previews}, "result": (paths,)}


NODE_CLASS_MAPPINGS = {"XavierSaveImage": XavierSaveImage}
NODE_DISPLAY_NAME_MAPPINGS = {"XavierSaveImage": "Save Image (XavierLAB)"}
