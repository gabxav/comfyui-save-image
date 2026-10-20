import importlib.util
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch
from PIL import Image

# Discover ComfyUI when installed under custom_nodes. For a standalone checkout,
# expose the ComfyUI root through PYTHONPATH using the same Python environment.
for parent in Path(__file__).resolve().parents:
    if (parent / "folder_paths.py").is_file() and (parent / "comfy").is_dir():
        sys.path.insert(0, str(parent))
        break
spec = importlib.util.spec_from_file_location(
    "xavier_save_test", Path(__file__).resolve().parents[1] / "__init__.py",
    submodule_search_locations=[str(Path(__file__).resolve().parents[1])])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
nodes = sys.modules["xavier_save_test.custom_node.nodes"]
saving = sys.modules["xavier_save_test.custom_node.saving"]


class SaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = patch.object(nodes.folder_paths, "get_output_directory", return_value=str(self.root))
        self.output.start()
        self.addCleanup(self.output.stop)
        self.metadata = patch.object(nodes.args, "disable_metadata", False)
        self.metadata.start()
        self.addCleanup(self.metadata.stop)
        self.node = nodes.XavierSaveImage()
        self.images = torch.linspace(0, 1, 32 * 32 * 3).reshape(1, 32, 32, 3)
        self.workflow = {"nodes": [{"id": 1, "type": "XavierSaveImage"}]}
        self.prompt = {"1": {"class_type": "XavierSaveImage", "inputs": {}}}

    def save(self, **kwargs):
        return self.node.save(kwargs.pop("images", self.images), **kwargs)

    def test_png_pixels_batch_paths_metadata_and_input_unchanged(self):
        batch = torch.cat([self.images, 1 - self.images])
        original = batch.clone()
        result = self.save(images=batch, output_folder="portraits/products", filename_prefix="shirt",
                           prompt=self.prompt, extra_pnginfo={"workflow": self.workflow})
        self.assertEqual(len(result["result"][0]), 2)
        for i, path in enumerate(result["result"][0]):
            with Image.open(path) as image:
                self.assertEqual(image.format, "PNG")
                np.testing.assert_array_equal(np.array(image), (original[i].numpy() * 255).astype("uint8"))
                self.assertEqual(json.loads(image.info["workflow"]), self.workflow)
                self.assertEqual(json.loads(image.info["prompt"]), self.prompt)
            self.assertEqual(result["ui"]["images"][i]["subfolder"], "portraits/products")
        self.assertTrue(torch.equal(batch, original))

    def test_png_compression_is_lossless_and_effective(self):
        flat = torch.full((1, 128, 128, 3), 0.5)
        paths = [Path(self.save(images=flat, png_compression=c)["result"][0][0]) for c in (0, 9)]
        self.assertLess(paths[1].stat().st_size, paths[0].stat().st_size)
        with Image.open(paths[0]) as a, Image.open(paths[1]) as b:
            np.testing.assert_array_equal(np.array(a), np.array(b))

    def test_jpeg_quality_and_sidecar(self):
        noise = torch.rand((1, 128, 128, 3), generator=torch.Generator().manual_seed(12))
        paths = [Path(self.save(images=noise, format="JPEG", jpeg_quality=q, prompt=self.prompt,
                               extra_pnginfo={"workflow": self.workflow})["result"][0][0]) for q in (20, 95)]
        self.assertLess(paths[0].stat().st_size, paths[1].stat().st_size)
        for path in paths:
            with Image.open(path) as image:
                self.assertEqual((image.format, image.mode, image.size), ("JPEG", "RGB", (128, 128)))
            self.assertEqual(json.loads(path.with_suffix(".json").read_text())["workflow"], self.workflow)

    def test_alpha_and_grayscale(self):
        rgba = torch.zeros((1, 16, 16, 4))
        rgba[..., 0] = 1
        for fmt in ("PNG", "JPEG"):
            path = self.save(images=rgba, format=fmt)["result"][0][0]
            with Image.open(path) as image:
                self.assertEqual(image.getpixel((0, 0)), (255, 0, 0, 0) if fmt == "PNG" else (255, 255, 255))
        path = self.save(images=torch.ones((1, 5, 7, 1)))["result"][0][0]
        with Image.open(path) as image:
            self.assertEqual((image.mode, image.size), ("L", (7, 5)))

    def test_metadata_disabled_locally_and_globally(self):
        for global_disabled, local_enabled in ((False, False), (True, True)):
            with patch.object(nodes.args, "disable_metadata", global_disabled):
                for fmt in ("PNG", "JPEG"):
                    path = Path(self.save(format=fmt, save_metadata=local_enabled,
                                          extra_pnginfo={"workflow": self.workflow})["result"][0][0])
                    self.assertFalse(path.with_suffix(".json").exists())
                    with Image.open(path) as image:
                        self.assertNotIn("workflow", image.info)

    def test_collisions_concurrency_and_unicode(self):
        existing = self.root / "café_00001.jpg"
        existing.write_bytes(b"keep")
        orphan = self.root / "café_00003.json"
        orphan.write_text("keep")
        with ThreadPoolExecutor(max_workers=6) as pool:
            paths = list(pool.map(lambda _: self.save(format="JPEG", filename_prefix="café")["result"][0][0], range(12)))
        self.assertEqual(len(set(paths)), 12)
        self.assertEqual(existing.read_bytes(), b"keep")
        self.assertEqual(orphan.read_text(), "keep")
        for path in paths:
            with Image.open(path) as image:
                image.load()
            self.assertTrue(Path(path).with_suffix(".json").is_file())

    def test_reject_escape_and_invalid_prefix(self):
        for folder in ("../escape", "/tmp", "a/../../escape", "C:\\outside"):
            with self.assertRaises(ValueError):
                self.save(output_folder=folder)
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "link").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.save(output_folder="link")
        for prefix in ("", "..", "a/b", "a\\b", "a\x00b"):
            with self.assertRaises(ValueError):
                self.save(filename_prefix=prefix)

    def test_failed_write_cleans_its_own_reservations(self):
        with patch.object(saving.Image.Image, "save", side_effect=OSError("Disk full")):
            with self.assertRaises(OSError):
                self.save(format="JPEG")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_nonfinite_values_and_invalid_shapes(self):
        values = torch.tensor([[[[float("nan"), float("inf"), float("-inf")]]]])
        path = self.save(images=values)["result"][0][0]
        with Image.open(path) as image:
            self.assertEqual(image.getpixel((0, 0)), (0, 255, 0))
        self.assertTrue(torch.isnan(values[0, 0, 0, 0]))
        for shape in ((0, 2, 2, 3), (1, 0, 2, 3), (1, 2, 2, 2), (2, 2, 3)):
            with self.assertRaises(ValueError):
                self.save(images=torch.zeros(shape))

    def test_prompt_text_same_name_and_exact_bytes_for_each_batch_image(self):
        text = "  A café at sunset.\nNegative: blurry\n日本語 🖼️\r\n"
        for fmt in ("PNG", "JPEG"):
            result = self.save(images=self.images.repeat(2, 1, 1, 1), format=fmt,
                               save_prompt=True, prompt_text=text)
            for name in result["result"][0]:
                path = Path(name)
                self.assertEqual(path.with_suffix(".txt").read_bytes(), text.encode("utf-8"))
                with Image.open(path) as image:
                    image.load()
                self.assertEqual(path.with_suffix(".json").exists(), fmt == "JPEG")

    def test_prompt_default_off_and_explicit_export_without_metadata(self):
        for kwargs in ({}, {"save_prompt": False, "prompt_text": "Do not export"}):
            path = Path(self.save(**kwargs)["result"][0][0])
            self.assertFalse(path.with_suffix(".txt").exists())
        with patch.object(nodes.args, "disable_metadata", True):
            path = Path(self.save(format="JPEG", save_metadata=False,
                                 save_prompt=True, prompt_text="Explicit prompt")["result"][0][0])
        self.assertFalse(path.with_suffix(".json").exists())
        self.assertEqual(path.with_suffix(".txt").read_text(), "Explicit prompt")

    def test_empty_prompt_rejected_before_writing(self):
        for text in ("", " \n\t", None):
            with self.assertRaisesRegex(ValueError, "prompt_text"):
                self.save(save_prompt=True, prompt_text=text)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_concurrent_prompt_pairs_and_existing_text_are_preserved(self):
        orphan = self.root / "ComfyUI_00001.txt"
        orphan.write_text("Existing text")
        def save_pair(index):
            text = f"Prompt {index}"
            path = Path(self.save(format="JPEG", save_prompt=True, prompt_text=text)["result"][0][0])
            return path, text
        with ThreadPoolExecutor(max_workers=6) as pool:
            pairs = list(pool.map(save_pair, range(12)))
        self.assertEqual(len({path for path, _ in pairs}), 12)
        for path, text in pairs:
            self.assertEqual(path.with_suffix(".txt").read_text(), text)
            self.assertTrue(path.is_file())
            self.assertTrue(path.with_suffix(".json").is_file())
        self.assertEqual(orphan.read_text(), "Existing text")

    def test_failed_text_write_cleans_image_and_json(self):
        original = saving.atomic_write
        def fail_text(path, writer):
            if path.suffix == ".txt":
                raise OSError("Text write failed")
            return original(path, writer)
        for fmt in ("PNG", "JPEG"):
            with patch.object(saving, "atomic_write", side_effect=fail_text):
                with self.assertRaisesRegex(OSError, "Text write failed"):
                    self.save(format=fmt, save_prompt=True, prompt_text="A portrait")
            self.assertEqual(list(self.root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
