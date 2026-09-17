# Local image generation

The Auto Video Generator uses this PC's ComfyUI instance for every generated
scene image. It reads the connection and workflow from `settings.json`:

- `image_generator`: `comfyui`
- `comfyui_url`: the local ComfyUI API address (normally `http://127.0.0.1:8188`)
- `image_workflow`: the API-format workflow to queue

When a video job starts, the app checks ComfyUI, starts it from the configured
local launcher when needed, then queues each scene through the configured
workflow. Generated job files stay under `runtime/jobs/` on this PC and are
excluded from Git.
