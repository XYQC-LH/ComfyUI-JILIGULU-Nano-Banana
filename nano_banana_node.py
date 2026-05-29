from __future__ import annotations

import io
import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_POLL_TIMEOUT_SECONDS = 900
DEFAULT_POLL_INTERVAL_SECONDS = 5
TERMINAL_STATUSES = {"succeeded", "completed", "success", "failed", "cancelled", "canceled", "timeout"}
SUCCESS_STATUSES = {"succeeded", "completed", "success"}
DEFAULT_BASE_URL = "https://jiligulu.art"
NANO_BANANA_MODELS = {
    "nano-banana": {
        "display_name": "JILIGULU Nano Banana",
        "image_sizes": ("1K", "2K", "4K"),
        "max_images": 10,
    },
    "nano-banana-fast": {
        "display_name": "JILIGULU Nano Banana Fast",
        "image_sizes": ("1K", "2K", "4K"),
        "max_images": 1,
    },
    "nano-banana-pro": {
        "display_name": "JILIGULU Nano Banana Pro",
        "image_sizes": ("1K", "2K", "4K"),
        "max_images": 8,
    },
    "nano-banana-2": {
        "display_name": "JILIGULU Nano Banana 2",
        "image_sizes": ("1K", "2K"),
        "max_images": 14,
    },
}
GLOBAL_MAX_REFERENCE_INPUTS = max(model["max_images"] for model in NANO_BANANA_MODELS.values())
ASPECT_RATIOS = ("auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9")


class JiliguluApiError(RuntimeError):
    pass


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _build_headers(api_key: str | None = None) -> dict[str, str]:
    api_key = str(api_key or "").strip() or _env("JILIGULU_API_KEY")
    if not api_key:
        raise JiliguluApiError("缺少 api_key，且环境变量 JILIGULU_API_KEY 也未设置。")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    tenant_id = _env("JILIGULU_TENANT_ID")
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    return headers


def _resolve_base_url(base_url: str | None = None) -> str:
    return _env("JILIGULU_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _normalize_status(status: Any) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"completed", "success"}:
        return "succeeded"
    if normalized == "canceled":
        return "cancelled"
    return normalized


def _normalize_public_url(url: Any, base_url: str | None = None) -> str:
    value = str(url or "").strip()
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    return urljoin(f"{_resolve_base_url(base_url)}/", value.lstrip("/"))


def _is_same_origin(url: str, base_url: str | None = None) -> bool:
    target = urlparse(_normalize_public_url(url, base_url=base_url))
    base = urlparse(f"{_resolve_base_url(base_url)}/")
    return (
        target.scheme.lower(),
        target.netloc.lower(),
    ) == (
        base.scheme.lower(),
        base.netloc.lower(),
    )


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

    http_error_301 = HTTPRedirectHandler.http_error_302
    http_error_303 = HTTPRedirectHandler.http_error_302
    http_error_307 = HTTPRedirectHandler.http_error_302
    http_error_308 = HTTPRedirectHandler.http_error_302

    def http_error_302(self, req, fp, code, msg, headers):
        return fp


def _http_json(
    *,
    method: str,
    path: str,
    query: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    url = f"{_resolve_base_url(base_url)}{path}"
    if query:
        query_string = urlencode({key: str(value) for key, value in query.items() if value is not None})
        if query_string:
            url = f"{url}?{query_string}"

    headers = _build_headers(api_key=api_key)
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = Request(url=url, method=method.upper(), headers=headers, data=body)
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            text = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        raise JiliguluApiError(f"HTTP {exc.code}: {text}") from exc
    except (URLError, TimeoutError) as exc:
        raise JiliguluApiError("请求 JILIGULU API 失败，可能是网络异常或超时。") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise JiliguluApiError(f"API 返回了非 JSON 内容: {text}") from exc

    if not isinstance(data, dict):
        raise JiliguluApiError(f"API 返回格式异常: {data!r}")
    if data.get("success") is False:
        message = str(data.get("message") or data.get("error") or "API_ERROR").strip()
        raise JiliguluApiError(message)
    return data


def _build_multipart_body(file_name: str, file_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
    boundary = f"----JILIGULUBoundary{int(time.time() * 1000)}"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8")
    )
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return bytes(body), boundary


def _upload_asset(
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    url = f"{_resolve_base_url(base_url)}/api/v1/assets/upload"
    body, boundary = _build_multipart_body(file_name=file_name, file_bytes=file_bytes, mime_type=mime_type)
    headers = _build_headers(api_key=api_key)
    headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"

    request = Request(url=url, method="POST", headers=headers, data=body)
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            text = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        raise JiliguluApiError(f"HTTP {exc.code}: {text}") from exc
    except (URLError, TimeoutError) as exc:
        raise JiliguluApiError("上传图片资源失败，可能是网络异常或超时。") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise JiliguluApiError(f"上传接口返回了非 JSON 内容: {text}") from exc

    if not isinstance(data, dict):
        raise JiliguluApiError(f"上传接口返回格式异常: {data!r}")
    if data.get("success") is False:
        message = str(data.get("message") or data.get("error") or "API_ERROR").strip()
        raise JiliguluApiError(message)

    payload = data.get("data")
    if not isinstance(payload, dict):
        raise JiliguluApiError(f"上传接口 data 字段缺失: {data!r}")
    return payload


def _normalize_task(task: dict[str, Any], *, base_url: str | None = None) -> dict[str, Any]:
    output_groups = task.get("output_groups")
    if not isinstance(output_groups, list):
        output_groups = []

    outputs: list[dict[str, Any]] = []
    result_url = _normalize_public_url(task.get("result_url"), base_url=base_url)
    result = task.get("result")
    output_payload = task.get("output_payload")

    if isinstance(output_payload, dict) and not result_url:
        result_url = _normalize_public_url(
            output_payload.get("result_url") or output_payload.get("primary_result_url"),
            base_url=base_url,
        )

    if isinstance(result, dict) and not result_url:
        result_url = _normalize_public_url(result.get("url") or result.get("result_url"), base_url=base_url)

    for group in output_groups:
        if not isinstance(group, dict):
            continue
        items = group.get("items")
        if not isinstance(items, list):
            continue
        public_items: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            entry: dict[str, Any] = {}
            item_url = _normalize_public_url(item.get("url"), base_url=base_url)
            asset_id = str(item.get("assetId") or item.get("asset_id") or "").strip()
            if item_url:
                entry["url"] = item_url
                if not result_url:
                    result_url = item_url
            if asset_id:
                entry["assetId"] = asset_id
            if entry:
                public_items.append(entry)
        if public_items:
            outputs.append({"kind": group.get("kind"), "items": public_items})

    return {
        "task_id": str(task.get("task_id") or task.get("id") or ""),
        "status": _normalize_status(task.get("status")),
        "runtime_phase": task.get("runtime_phase"),
        "progress": task.get("progress"),
        "result_url": result_url,
        "failure_message_public": task.get("failure_message_public"),
        "outputs": outputs,
    }


def _extract_task(envelope: dict[str, Any], *, base_url: str | None = None) -> dict[str, Any]:
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise JiliguluApiError(f"API data 字段缺失: {envelope!r}")
    task = data.get("task") if isinstance(data.get("task"), dict) else data
    if not isinstance(task, dict):
        raise JiliguluApiError(f"任务信息缺失: {data!r}")
    return _normalize_task(task, base_url=base_url)


def _get_model_defaults(model_id: str, *, api_key: str | None = None, base_url: str | None = None) -> dict[str, Any]:
    envelope = _http_json(
        method="GET",
        path=f"/api/v1/models/{model_id}/config",
        api_key=api_key,
        base_url=base_url,
    )
    data = envelope.get("data")
    if not isinstance(data, dict):
        return {}
    defaults = data.get("default_params")
    return defaults if isinstance(defaults, dict) else {}


def _run_model(
    model_id: str,
    user_inputs: dict[str, Any],
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    envelope = _http_json(
        method="POST",
        path=f"/api/v1/models/{model_id}/run",
        payload={"user_inputs": user_inputs},
        api_key=api_key,
        base_url=base_url,
    )
    return _extract_task(envelope, base_url=base_url)


def _poll_task(
    task_id: str,
    timeout_seconds: int,
    interval_seconds: int,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    started_at = time.time()

    while True:
        envelope = _http_json(
            method="GET",
            path=f"/api/v1/tasks/{task_id}",
            query={"include_media_urls": "true"},
            api_key=api_key,
            base_url=base_url,
        )
        task = _extract_task(envelope, base_url=base_url)
        status = _normalize_status(task.get("status"))
        if status in TERMINAL_STATUSES:
            return task
        if time.time() - started_at >= timeout_seconds:
            task["timed_out"] = True
            return task
        time.sleep(interval_seconds)


def _download_image(url: str, *, api_key: str | None = None, base_url: str | None = None) -> Any:
    import numpy as np
    import torch
    from PIL import Image

    normalized_url = _normalize_public_url(url, base_url=base_url)

    def _read_image_bytes(target_url: str, headers: dict[str, str], *, follow_redirects: bool) -> bytes:
        request = Request(url=target_url, method="GET", headers=headers)
        opener = build_opener() if follow_redirects else build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, "status", response.getcode()) or 200)
            if not follow_redirects and status in {301, 302, 303, 307, 308}:
                redirect_url = _normalize_public_url(response.headers.get("Location"), base_url=base_url)
                if not redirect_url:
                    raise JiliguluApiError("下载图片失败，重定向响应缺少 Location。")
                return _read_image_bytes(redirect_url, {"Accept": "image/*"}, follow_redirects=True)
            return response.read()

    try:
        if _is_same_origin(normalized_url, base_url=base_url):
            headers = _build_headers(api_key=api_key)
            headers["Accept"] = "image/*"
            image_bytes = _read_image_bytes(normalized_url, headers, follow_redirects=False)
        else:
            image_bytes = _read_image_bytes(normalized_url, {"Accept": "image/*"}, follow_redirects=True)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        if detail:
            raise JiliguluApiError(f"下载图片失败，HTTP {exc.code}: {detail}") from exc
        raise JiliguluApiError(f"下载图片失败，HTTP {exc.code}。") from exc
    except (URLError, TimeoutError) as exc:
        raise JiliguluApiError("下载图片失败，可能是网络异常或超时。") from exc

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise JiliguluApiError("图片解码失败。") from exc

    image_array = np.asarray(image).astype(np.float32) / 255.0
    return torch.from_numpy(image_array).unsqueeze(0)


def _image_tensor_to_png_bytes(image: Any) -> bytes:
    import numpy as np
    from PIL import Image

    if image is None:
        raise JiliguluApiError("image 输入为空。")

    if hasattr(image, "detach"):
        image = image.detach()
    if hasattr(image, "cpu"):
        image = image.cpu()
    if hasattr(image, "numpy"):
        image = image.numpy()

    image_array = np.asarray(image)
    if image_array.ndim == 4:
        image_array = image_array[0]
    if image_array.ndim != 3 or image_array.shape[-1] < 3:
        raise JiliguluApiError("image 输入格式不符合 ComfyUI IMAGE 规范。")

    image_array = np.clip(image_array[..., :3], 0.0, 1.0)
    image_uint8 = (image_array * 255.0).round().astype(np.uint8)
    pil_image = Image.fromarray(image_uint8, mode="RGB")
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    return buffer.getvalue()


def _build_optional_image_inputs() -> dict[str, tuple[str]]:
    optional_inputs: dict[str, tuple[str]] = {"image": ("IMAGE",)}
    for index in range(2, GLOBAL_MAX_REFERENCE_INPUTS + 1):
        optional_inputs[f"image_{index}"] = ("IMAGE",)
    return optional_inputs


def _iter_images_from_value(value: Any) -> list[Any]:
    if value is None:
        return []
    shape = getattr(value, "shape", None)
    if shape is None:
        raise JiliguluApiError("image 输入格式异常。")

    dims = len(shape)
    if dims == 3:
        return [value]
    if dims == 4:
        return [value[index : index + 1] for index in range(int(shape[0]))]
    raise JiliguluApiError("image 输入格式不符合 ComfyUI IMAGE 规范。")


def _collect_input_images(kwargs: dict[str, Any]) -> list[Any]:
    images: list[Any] = []
    for index in range(1, GLOBAL_MAX_REFERENCE_INPUTS + 1):
        key = "image" if index == 1 else f"image_{index}"
        image = kwargs.get(key)
        if image is None:
            continue
        images.extend(_iter_images_from_value(image))
    return images


class _JiliguluNanoBananaBaseNode:
    MODEL_ID = ""
    DISPLAY_NAME = ""
    IMAGE_SIZES: tuple[str, ...] = ()
    MAX_IMAGES = 1

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "api_key": ("STRING", {"default": ""}),
                "aspect_ratio": (list(ASPECT_RATIOS), {"default": "auto"}),
                "image_size": (list(cls.IMAGE_SIZES), {"default": cls.IMAGE_SIZES[0]}),
            },
            "optional": _build_optional_image_inputs(),
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "generate"
    CATEGORY = "JILIGULU"

    def generate(
        self,
        prompt: str,
        api_key: str,
        aspect_ratio: str,
        image_size: str,
        **kwargs: Any,
    ) -> tuple[Any]:
        prompt = str(prompt or "").strip()
        if not prompt:
            raise JiliguluApiError("prompt 不能为空。")

        model_info = NANO_BANANA_MODELS.get(self.MODEL_ID)
        if model_info is None:
            raise JiliguluApiError("当前节点只允许接入 Nano Banana 系列模型。")

        image_size = str(image_size or "").strip()
        if image_size not in model_info["image_sizes"]:
            allowed = ", ".join(model_info["image_sizes"])
            raise JiliguluApiError(f"{self.MODEL_ID} 仅支持这些 image_size: {allowed}。")

        resolved_base_url = _resolve_base_url()
        api_key = str(api_key or "").strip()
        default_params = _get_model_defaults(self.MODEL_ID, api_key=api_key, base_url=resolved_base_url)
        user_inputs = dict(default_params)
        user_inputs["prompt"] = prompt
        user_inputs["aspect_ratio"] = str(aspect_ratio or "auto").strip() or "auto"
        user_inputs["image_size"] = image_size
        user_inputs["shut_progress"] = False

        input_images = _collect_input_images(kwargs)
        if len(input_images) > self.MAX_IMAGES:
            raise JiliguluApiError(f"{self.MODEL_ID} 最多支持 {self.MAX_IMAGES} 张参考图。")
        if input_images:
            image_urls: list[str] = []
            for index, input_image in enumerate(input_images, start=1):
                uploaded_image = _upload_asset(
                    file_bytes=_image_tensor_to_png_bytes(input_image),
                    file_name=f"{self.MODEL_ID}-reference-{index}.png",
                    mime_type="image/png",
                    api_key=api_key,
                    base_url=resolved_base_url,
                )
                image_url = str(uploaded_image.get("url") or "").strip()
                if not image_url:
                    raise JiliguluApiError("图片上传成功，但返回里没有 url。")
                image_urls.append(image_url)
            user_inputs["urls"] = image_urls

        task = _run_model(self.MODEL_ID, user_inputs, api_key=api_key, base_url=resolved_base_url)
        task_id = str(task.get("task_id") or "").strip()
        if not task_id:
            raise JiliguluApiError("创建任务成功，但响应里缺少 task_id。")

        task = _poll_task(
            task_id=task_id,
            timeout_seconds=DEFAULT_POLL_TIMEOUT_SECONDS,
            interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS,
            api_key=api_key,
            base_url=resolved_base_url,
        )

        status = _normalize_status(task.get("status"))
        if task.get("timed_out"):
            raise JiliguluApiError(f"任务轮询超时，task_id={task_id}。")
        if status not in SUCCESS_STATUSES:
            message = str(task.get("failure_message_public") or f"任务状态为 {status}。").strip()
            raise JiliguluApiError(message)

        result_url = str(task.get("result_url") or "").strip()
        if not result_url:
            raise JiliguluApiError("任务已完成，但没有拿到结果图片 URL。")

        image_tensor = _download_image(result_url, api_key=api_key, base_url=resolved_base_url)
        return (image_tensor,)


class JiliguluNanoBananaNode(_JiliguluNanoBananaBaseNode):
    MODEL_ID = "nano-banana"
    DISPLAY_NAME = NANO_BANANA_MODELS[MODEL_ID]["display_name"]
    IMAGE_SIZES = NANO_BANANA_MODELS[MODEL_ID]["image_sizes"]
    MAX_IMAGES = NANO_BANANA_MODELS[MODEL_ID]["max_images"]


class JiliguluNanoBananaFastNode(_JiliguluNanoBananaBaseNode):
    MODEL_ID = "nano-banana-fast"
    DISPLAY_NAME = NANO_BANANA_MODELS[MODEL_ID]["display_name"]
    IMAGE_SIZES = NANO_BANANA_MODELS[MODEL_ID]["image_sizes"]
    MAX_IMAGES = NANO_BANANA_MODELS[MODEL_ID]["max_images"]


class JiliguluNanoBananaProNode(_JiliguluNanoBananaBaseNode):
    MODEL_ID = "nano-banana-pro"
    DISPLAY_NAME = NANO_BANANA_MODELS[MODEL_ID]["display_name"]
    IMAGE_SIZES = NANO_BANANA_MODELS[MODEL_ID]["image_sizes"]
    MAX_IMAGES = NANO_BANANA_MODELS[MODEL_ID]["max_images"]


class JiliguluNanoBanana2Node(_JiliguluNanoBananaBaseNode):
    MODEL_ID = "nano-banana-2"
    DISPLAY_NAME = NANO_BANANA_MODELS[MODEL_ID]["display_name"]
    IMAGE_SIZES = NANO_BANANA_MODELS[MODEL_ID]["image_sizes"]
    MAX_IMAGES = NANO_BANANA_MODELS[MODEL_ID]["max_images"]


NODE_CLASS_MAPPINGS = {
    "JiliguluNanoBananaNode": JiliguluNanoBananaNode,
    "JiliguluNanoBananaFastNode": JiliguluNanoBananaFastNode,
    "JiliguluNanoBananaProNode": JiliguluNanoBananaProNode,
    "JiliguluNanoBanana2Node": JiliguluNanoBanana2Node,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "JiliguluNanoBananaNode": JiliguluNanoBananaNode.DISPLAY_NAME,
    "JiliguluNanoBananaFastNode": JiliguluNanoBananaFastNode.DISPLAY_NAME,
    "JiliguluNanoBananaProNode": JiliguluNanoBananaProNode.DISPLAY_NAME,
    "JiliguluNanoBanana2Node": JiliguluNanoBanana2Node.DISPLAY_NAME,
}
