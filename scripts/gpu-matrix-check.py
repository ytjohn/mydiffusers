import torch
import time
print("torch:", torch.__version__)
print("hip:", torch.version.hip)
print("cuda string (expected None or empty):", torch.version.cuda)

print("Testing matrix multiplication...")
x = torch.randn(4096, 4096, device="cuda", dtype=torch.float16)
y = torch.randn(4096, 4096, device="cuda", dtype=torch.float16)
torch.cuda.synchronize()
t0=time.time()
for _ in range(50):
    z = x @ y
torch.cuda.synchronize()
print("secs:", time.time()-t0, "result:", z[0,0].item())
