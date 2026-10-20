# Save Image (XavierLAB)

ComfyUI output node for saving IMAGE batches as compressed PNG or JPEG.
Search for **Save Image (XavierLAB)** or **xavierlab**.

Works with a standard ComfyUI installation and its configured output directory.
No account, API key, external service, model or XavierLAB infrastructure is required.
Descriptions, tooltips and error messages are in English.

| Input | Default | Behavior |
| --- | --- | --- |
| images | required | IMAGE batch; grayscale, RGB or RGBA |
| format | PNG | PNG or JPEG (.jpg) |
| filename_prefix | ComfyUI | Filename prefix without directories |
| output_folder | empty | Subfolder inside the configured ComfyUI output directory |
| png_compression | 6 | 0–9; lossless PNG compression |
| jpeg_quality | 90 | 1–100; lossy JPEG quality |
| save_metadata | true | PNG embedded metadata or JPEG companion JSON |
| save_prompt | false | Save the supplied prompt in a .txt file beside each image |
| prompt_text | empty | Multiline prompt text; can also be connected from a STRING output |

Only the selected format's compression control is shown. When format is supplied
by a connected input, both controls remain available.

`output_folder=portraits/session` and `filename_prefix=portrait` produce
`portraits/session/portrait_00001.png` inside ComfyUI's output directory.
Directories are created automatically. Absolute paths, parent traversal and
symlinks escaping the output directory are rejected. Files are reserved with
exclusive creation and written through temporary files to avoid overwriting
existing results, including concurrent saves. Errors are surfaced to ComfyUI.
Earlier successfully saved batch images remain if a later image fails.

The node preserves resolution, exports 8 bits per channel and does not modify
input tensors. PNG preserves alpha; JPEG composites RGBA on white and uses
optimized encoding with 4:4:4 chroma sampling. Higher PNG compression can take
more time; JPEG quality above 95 usually adds substantial size for little gain.
Metadata preserves ComfyUI prompt and workflow, respecting `--disable-metadata`.
JPEG workflow recovery uses the companion JSON's `workflow` object; JPEG itself
does not contain an embedded workflow.

Enable **save_prompt** and type or connect **prompt_text** to save a plain-text
prompt alongside the image. For example, `portrait_00001.png` is paired with
`portrait_00001.txt`; JPEG uses the same convention. Text is saved exactly as
supplied in UTF-8, preserving whitespace, line breaks and Unicode characters.
An empty or whitespace-only prompt is rejected before saving images.

Every image in one IMAGE batch receives the same supplied text. For different
prompts per image, pass each matching image and prompt through separate node
executions. The node does not guess or extract a positive prompt from the workflow.
This explicit text export is independent of `save_metadata` and
`--disable-metadata`. TXT, image and optional JSON filenames are reserved together;
existing companions are never overwritten. If writing a companion fails, files
created for that image are cleaned up and the error is reported.
Existing workflows keep their previous behavior because **save_prompt** defaults
to false.

The `file_paths` STRING list output contains one absolute **server** path per
image. Saved images are also returned through ComfyUI's standard preview/history
contract. A server output directory is not a folder on the browser's computer.

## Installation

From your ComfyUI directory:

```bash
git clone https://github.com/gabxav/comfyui-save-image.git custom_nodes/comfyui-save-image
```

Alternatively, download the repository and place it at
`ComfyUI/custom_nodes/comfyui-save-image`. Restart ComfyUI with its queue empty,
then reload the browser. Uses the Python, PyTorch, Pillow and NumPy dependencies
already provided by ComfyUI. No additional dependencies are installed.

## Example workflow

Drag `examples/save_png_jpeg.json` into ComfyUI, then click **Run**. It uses
Empty Image with a batch of two and one save node for each format. It needs no
models and saves two PNGs, two JPEGs and their companion JSON files inside
`output/save-image-example/` (relative to your configured output directory).
Connect any IMAGE-producing node in place of Empty Image to save your own images.

`examples/save_png_jpeg_with_prompt.json` enables text export on both save nodes
and includes an editable sample prompt. It also produces one matching .txt file
per image. Empty Image is only a test image source; the sample text does not
generate an image.

## Validation

From this package directory, run with the Python interpreter used by ComfyUI:

```bash
python -m unittest discover -s tests -v
```

Tests cover encoding, alpha, metadata, batch behavior, filename collisions,
concurrent saves, directory restrictions, failed writes and tensor preservation.
Prompt tests verify exact UTF-8 text, batch pairing, default-off compatibility,
empty prompt validation, concurrent companions and cleanup after text-write failure.
The tests discover the ComfyUI root when installed under `custom_nodes`.
For a standalone checkout, add your ComfyUI root to `PYTHONPATH`.

`tests/browser_smoke.js` is a Playwright CLI smoke test for an already opened
ComfyUI page. Use a dedicated browser session: it replaces the current graph
and queues a small example batch in `save-image-validation/`.

## License

[MIT](LICENSE)
