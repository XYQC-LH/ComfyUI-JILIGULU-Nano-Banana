# JILIGULU Nano Banana ComfyUI Nodes

这个目录提供一组 `Nano Banana` 系列的 ComfyUI 自定义节点，走的是 JILIGULU 用户态模型接口。

当前提供的节点：

- `JILIGULU Nano Banana`
- `JILIGULU Nano Banana Fast`
- `JILIGULU Nano Banana Pro`
- `JILIGULU Nano Banana 2`

## 环境变量

启动 ComfyUI 前可以先设置：

```powershell
$env:JILIGULU_API_KEY = "your-api-key"
$env:JILIGULU_BASE_URL = "https://jiligulu.art"
$env:JILIGULU_TENANT_ID = "optional-tenant-id"
```

说明：

- `JILIGULU_API_KEY` 可以直接填在节点里，也可以走环境变量
- `JILIGULU_BASE_URL` 不会在节点面板里暴露，但运行时会按环境变量读取；未设置时默认走 `https://jiligulu.art`
- `JILIGULU_TENANT_ID` 按需填写

## 请求链路

节点内部请求顺序与主插件保持一致：

1. `GET /api/v1/models/{model_id}/config`
2. `POST /api/v1/assets/upload`
3. `POST /api/v1/models/{model_id}/run`
4. `GET /api/v1/tasks/{task_id}?include_media_urls=true`
5. 下载结果图并转成 ComfyUI `IMAGE`

## 输出

每个节点只输出 1 个值：

1. `image`

## 当前实现范围

目前对接的模型 ID：

- `nano-banana`
- `nano-banana-fast`
- `nano-banana-pro`
- `nano-banana-2`

模型限制：

- `nano-banana`：最多 `10` 张参考图，支持 `1K / 2K / 4K`
- `nano-banana-fast`：最多 `1` 张参考图，支持 `1K / 2K / 4K`
- `nano-banana-pro`：最多 `8` 张参考图，支持 `1K / 2K / 4K`
- `nano-banana-2`：最多 `14` 张参考图，支持 `1K / 2K`

## 示例

- 纯文生图：`examples/text-to-image/workflow.json`
- 单参考图：`examples/single-reference/workflow.json`

对应预览图：

- `examples/text-to-image/preview.png`
- `examples/single-reference/preview.png`

## 使用说明

- 节点里可以直接填写 `api_key`
- 参考图输入支持从 `image` 一直到 `image_14`
- 如果某个模型超出自身张数上限，节点会在本地直接报错，不会把非法请求发到后端

如果你只是第一次测试，建议先按这个顺序：

1. 导入 `examples/text-to-image/workflow.json`
2. 在节点里填写 `api_key`
3. 先跑通纯文生图
4. 再导入 `examples/single-reference/workflow.json` 测试带参考图的场景
