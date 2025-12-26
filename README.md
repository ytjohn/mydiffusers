
Need rocm7.0 for 395+ support.

```shell
python - <<'PY'
import torch
print("hip:", torch.version.hip)
print("arch list:", getattr(torch.cuda, "get_arch_list", lambda: None)())
print("device:", torch.cuda.get_device_name(0))
PY
hip: 6.3.42134-a9a80e791
/opt/amdgpu/share/libdrm/amdgpu.ids: No such file or directory
arch list: ['gfx900', 'gfx906', 'gfx908', 'gfx90a', 'gfx942', 'gfx1030', 'gfx1100', 'gfx1101', 'gfx1102', 'gfx1200', 'gfx1201']
device: AMD Radeon 8060S
```

```shell
mydiffuser main  ? ✗ uv pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/rocm7.0
```



```
INFO:server:Pipeline warmup completed in 100.71s
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     127.0.0.1:51110 - "GET / HTTP/1.1" 200 OK
INFO:     127.0.0.1:51110 - "GET /favicon.ico HTTP/1.1" 404 Not Found
INFO:server:Generate preset=draft h=832 w=832 steps=4 guidance=0.00 seed=42
100%|█████████████████████████████████████████████████████████████████████████████████████████████████████| 4/4 [00:13<00:00,  3.42s/it]

INFO:server:Saved outputs/run/image/c548c38d-5429-4495-995a-c547284e3bbd/output.png in 287.21s
INFO:     127.0.0.1:56054 - "POST /generate_image HTTP/1.1" 200 OK
INFO:server:Generate preset=draft h=832 w=832 steps=4 guidance=0.00 seed=89
100%|█████████████████████████████████████████████████████████████████████████████████████████| 4/4 [00:13<00:00,  3.39s/it]
INFO:server:Saved outputs/run/image/a974d365-a7d4-4bd8-a3e2-17ed75aefeea/output.png in 18.58s
INFO:     127.0.0.1:35644 - "POST /generate_image HTTP/1.1" 200 OK


INFO:server:Generate preset=final h=1024 w=1024 steps=9 guidance=1.00 seed=42
100%|█████████████████████████████████████████████████████████████████████████████████████████| 9/9 [01:21<00:00,  9.05s/it]
^C^C^C^CINFO:server:Saved outputs/run/image/076857b3-7bd5-4a6a-a8b7-89cd310e4a0f/output.png in 486.22s
```