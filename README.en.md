# JILIGULU Nano Banana ComfyUI Nodes

[简体中文](README.md) | English

This directory provides a set of ComfyUI custom nodes for the `Nano Banana` model family through the JILIGULU user-facing model API.

Currently included nodes:

- `JILIGULU Nano Banana`
- `JILIGULU Nano Banana Fast`
- `JILIGULU Nano Banana Pro`
- `JILIGULU Nano Banana 2`

## Environment Variables

Before starting ComfyUI, you can set:

```powershell
$env:JILIGULU_API_KEY = "your-api-key"
$env:JILIGULU_BASE_URL = "https://jiligulu.art"
$env:JILIGULU_TENANT_ID = "optional-tenant-id"
```

Notes:

- `JILIGULU_API_KEY` can be filled directly in the node or provided via environment variable
- `JILIGULU_BASE_URL` is not exposed in the node UI, but the runtime reads it from the environment; if unset, it falls back to `https://jiligulu.art`
- `JILIGULU_TENANT_ID` is optional

## Request Flow

The internal request sequence is aligned with the main plugin:

1. `GET /api/v1/models/{model_id}/config`
2. `POST /api/v1/assets/upload`
3. `POST /api/v1/models/{model_id}/run`
4. `GET /api/v1/tasks/{task_id}?include_media_urls=true`
5. Download the resulting image and convert it into a ComfyUI `IMAGE`

## Output

Each node returns only one output:

1. `image`

## Supported Models

Current model IDs:

- `nano-banana`
- `nano-banana-fast`
- `nano-banana-pro`
- `nano-banana-2`

Model limits:

- `nano-banana`: up to `10` reference images, supports `1K / 2K / 4K`
- `nano-banana-fast`: up to `1` reference image, supports `1K / 2K / 4K`
- `nano-banana-pro`: up to `8` reference images, supports `1K / 2K / 4K`
- `nano-banana-2`: up to `14` reference images, supports `1K / 2K`

## Examples

- Text to image: `examples/text-to-image/workflow.json`
- Single reference: `examples/single-reference/workflow.json`

Preview images:

- `examples/text-to-image/preview.png`
- `examples/single-reference/preview.png`

## Usage

- Fill in `api_key` directly in the node
- Reference image inputs are available from `image` to `image_14`
- If a model exceeds its own image count limit, the node fails locally before sending an invalid request to the backend

For a first test, this order is recommended:

1. Import `examples/text-to-image/workflow.json`
2. Fill in your `api_key`
3. Run a plain text-to-image example first
4. Then import `examples/single-reference/workflow.json` to test an image-conditioned flow
