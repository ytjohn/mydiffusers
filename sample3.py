import numpy as np
import torch
from diffusers import ZImagePipeline
from PIL import Image

DEVICE = "mps"
DTYPE = torch.bfloat16

pipe = ZImagePipeline.from_pretrained(
    "Tongyi-MAI/Z-Image-Turbo",
    torch_dtype=DTYPE,
    low_cpu_mem_usage=False,
).to(DEVICE)

prompt = "Young Chinese woman in red Hanfu, intricate embroidery. Impeccable makeup, red floral forehead pattern. Elaborate high bun, golden phoenix headdress, red flowers, beads. Holds round folding fan with lady, trees, bird. Neon lightning-bolt lamp (⚡️), bright yellow glow, above extended left palm. Soft-lit outdoor night background, silhouetted tiered pagoda (西安大雁塔), blurred colorful distant lights."

out = pipe(
    prompt=prompt,
    height=1024,
    width=1024,
    num_inference_steps=9,
    guidance_scale=0.0,
    generator=torch.Generator(DEVICE).manual_seed(42),
    output_type="np",
)

img = out.images[0]
# img = np.nan_to_num(img, nan=0.0, posinf=1.0, neginf=0.0)
# img = np.clip(img, 0.0, 1.0)

Image.fromarray((img * 255).round().astype("uint8")).save("example.png")

