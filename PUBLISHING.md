# Publishing

This note is for maintainers publishing `Nano Banana` to Comfy Registry.

## Registry Metadata

Current Registry package name:

```text
jiligulu-nano-banana
```

Expected Publisher ID:

```text
xyqc-lh
```

Before publishing, make sure the Publisher ID exists in Comfy Registry:

```text
https://registry.comfy.org/
```

If the actual Publisher ID is different, update `PublisherId` in `pyproject.toml` before the first publish.

If the final GitHub repository path is different, update the `Icon` URL in `pyproject.toml` before publishing.

## Publish

Install `comfy-cli` in your publishing environment:

```bash
pip install comfy-cli
```

Publish from the repository root:

```bash
comfy node publish
```

The command will ask for a Comfy Registry API key. Create that key in Comfy Registry; it is different from the JILIGULU Agent Key used by the ComfyUI node.
