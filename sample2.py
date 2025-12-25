import os
import torch
from diffusers import ZImagePipeline

# Optional: allow fallback to CPU for unsupported MPS ops
# os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

DEVICE_TYPE = "mps"

# Safer default for MPS
DTYPE = torch.float32

pipe = ZImagePipeline.from_pretrained(
    "Tongyi-MAI/Z-Image-Turbo",
    torch_dtype=DTYPE,
    low_cpu_mem_usage=False,
).to(DEVICE_TYPE)

prompt = "Young Chinese woman in red Hanfu, intricate embroidery. Impeccable makeup, red floral forehead pattern. Elaborate high bun, golden phoenix headdress, red flowers, beads. Holds round folding fan with lady, trees, bird. Neon lightning-bolt lamp (⚡️), bright yellow glow, above extended left palm. Soft-lit outdoor night background, silhouetted tiered pagoda (西安大雁塔), blurred colorful distant lights."

image = pipe(
    prompt=prompt,
    height=1024,
    width=1024,
    num_inference_steps=9,
    guidance_scale=0.0,
    generator=torch.Generator("cpu").manual_seed(42),
).images[0]

image.save("example.png")

