# Video Resolution Implementation Summary

**Date**: 2025-12-30
**Feature**: Configurable Video Output Resolution for WAN2.2 I2V Pipeline

## Problem Solved

The WAN2.2 I2V pipeline was defaulting to 480p output because the `size` parameter was missing from the pipeline call. Now users can choose between 480p (faster) or 720p (native WAN2.2 quality) with automatic aspect ratio detection.

## Files Modified (7 total)

### 1. `src/mydiffuser/models/requests.py`
**Added resolution field to GenerateVideoRequest model** (after line 64):
```python
# Video output resolution - determines final video dimensions
resolution: Literal["480p", "720p"] | None = Field(
    None,
    description="Output resolution: 480p (832×480) or 720p (1280×704). Auto-detects aspect ratio.",
)
```

### 2. `src/mydiffuser/utils/presets.py`
**Change A**: Added resolution to VIDEO_PRESETS (lines 40-65):
- draft: `"resolution": "480p"`
- final: `"resolution": "720p"`
- hq: `"resolution": "720p"`

**Change B**: Updated `apply_video_preset()` (after line 165):
```python
if req.resolution is not None:
    base["resolution"] = req.resolution
```

### 3. `src/mydiffuser/generators/video/wan.py`
**Change A**: Added `_calculate_output_size()` helper function (after line 80):
```python
def _calculate_output_size(
    input_image: Image.Image, resolution: str = "480p"
) -> tuple[int, int]:
    """Calculate output video size based on input aspect ratio and resolution."""
    width, height = input_image.size
    is_landscape = width >= height

    if resolution == "720p":
        return (1280, 704) if is_landscape else (704, 1280)
    else:  # 480p
        return (832, 480) if is_landscape else (480, 832)
```

**Change B**: Added `resolution` parameter to `generate()` method signature (line 202):
```python
resolution: str = "480p",
```

**Change C**: Calculate size and log before pipeline call (after line 227):
```python
# Calculate output size based on input aspect ratio and resolution
output_size = _calculate_output_size(input_image, resolution)
logger.info(
    "%sOutput resolution: %s, detected %s orientation, size=%dx%d",
    log_prefix, resolution,
    "landscape" if output_size[0] > output_size[1] else "portrait",
    output_size[0], output_size[1],
)
```

**Change D**: Added `width` and `height` parameters to pipeline call (line 264-265):
```python
result = self._pipe(
    image=input_image,
    prompt=prompt,
    num_frames=num_frames,
    num_inference_steps=num_inference_steps,
    guidance_scale=guidance_scale,
    generator=generator,
    width=output_size[0],   # <-- ADDED THIS
    height=output_size[1],  # <-- ADDED THIS
    callback_on_step_end=final_callback,
    output_type="latent",
    return_dict=True,
)
```

**Note**: The WanImageToVideoPipeline uses separate `width` and `height` parameters, not a single `size` parameter. Both dimensions must be divisible by 16.

### 4. `src/mydiffuser/server/routes/video.py`
**Change A**: Pass resolution to generator (line 190):
```python
_, elapsed, num_frames = generator.generate(
    input_image=source_image,
    prompt=req.prompt,
    fps=params["fps"],
    duration_seconds=params["duration_seconds"],
    num_inference_steps=params["num_inference_steps"],
    guidance_scale=params["guidance_scale"],
    seed=req.seed,
    output_path=output_path,
    run_id=rid,
    resolution=params.get("resolution", "480p"),  # <-- ADDED THIS
)
```

**Change B**: Add resolution to metadata (line 218):
```python
"params": {
    "preset": req.preset,
    "seed": req.seed,
    "resolution": params.get("resolution", "480p"),  # <-- ADDED THIS
    "fps": params["fps"],
    # ... rest
},
```

### 5. `src/mydiffuser/client/templates/generate_video.html`
**Added resolution selector** (after line 289, before seed field):
```html
<div class="form-group">
    <label for="resolution">Output Resolution *</label>
    <select id="resolution" name="resolution" required>
        <option value="480p" selected>480p (832×480 / 480×832) - Faster</option>
        <option value="720p">720p (1280×704 / 704×1280) - Native WAN2.2</option>
    </select>
    <small style="color: #8b949e; display: block; margin-top: 4px;">
        Aspect ratio (landscape/portrait) is auto-detected from input image
    </small>
</div>
```

### 6. `src/mydiffuser/client/static/js/video_form.js`
**Change A**: Updated VIDEO_PRESETS (lines 2-6):
```javascript
const VIDEO_PRESETS = {
    draft: { duration: 3, fps: 12, steps: 15, guidance: 3.0, resolution: "480p" },
    final: { duration: 5, fps: 16, steps: 30, guidance: 3.5, resolution: "720p" },
    hq: { duration: 7, fps: 24, steps: 50, guidance: 4.0, resolution: "720p" },
};
```

**Change B**: Updated applyVideoPreset() (line 16):
```javascript
document.getElementById('resolution').value = preset.resolution;
```

### 7. `src/mydiffuser/client/routes.py`
No changes needed - API automatically picks up the new resolution field from the request model.

## Resolution Mapping

| Resolution | Landscape      | Portrait       | Use Case              |
|------------|----------------|----------------|-----------------------|
| 480p       | 832×480        | 480×832        | Fast iteration        |
| 720p       | 1280×704       | 704×1280       | Production quality    |

## Aspect Ratio Detection

- **Landscape**: width ≥ height → uses wider dimensions (1280×704 or 832×480)
- **Portrait**: height > width → uses taller dimensions (704×1280 or 480×832)
- **Square**: width == height → defaults to landscape

## Default Behavior & Backward Compatibility

- **Default resolution**: 480p (when not specified)
- **Preset defaults**:
  - draft → 480p (fast)
  - final → 720p (quality)
  - hq → 720p (maximum quality)
- **Existing API calls**: Continue to work (resolution is optional)
- **Old metadata files**: Gracefully handle missing resolution field

## How to Use

### Via UI (http://localhost:8000/generate/video)
1. Upload or select source image
2. Choose preset (draft/final/hq) - resolution auto-populates
3. OR manually select resolution from dropdown
4. Generate video

### Via API
```python
# POST /api/video
{
    "prompt": "gentle breathing, slight movement",
    "source_run_id": "20251230-012345-abc123",
    "preset": "final",
    "resolution": "720p"  # Optional - overrides preset default
}
```

## Testing Commands

```bash
# Check that client is running
curl http://localhost:8000/health

# Test video generation UI
# Visit: http://localhost:8000/generate/video

# Check logs for resolution detection
tail -f outputs/server.log | grep "Output resolution"
```

Expected log output:
```
[20251230-...] Output resolution: 720p, detected landscape orientation, size=1280x704
```

## Performance Notes

- **480p**: Faster generation, less VRAM (~10GB for 5B model)
- **720p**: 2-3x slower, 2.5x more VRAM (~16GB for 5B model), better quality
- **Native WAN2.2**: 720p is the model's native resolution for best results

## Troubleshooting

**Issue**: "Width must be divisible by 16" error
- **Solution**: This should no longer occur - the helper function ensures valid dimensions

**Issue**: Resolution doesn't change when selecting preset
- **Solution**: Check JavaScript console, ensure video_form.js was reloaded (hard refresh: Ctrl+Shift+R)

**Issue**: Still getting 480p output on 720p setting
- **Solution**:
  1. Check logs to confirm width/height parameters are being passed
  2. Ensure diffusers >= 0.36.0 is installed
  3. Restart worker if it's caching old pipeline

**Issue**: "WanImageToVideoPipeline.__call__() got an unexpected keyword argument 'size'"
- **Solution**: Fixed 2025-12-30 - Changed from `size=output_size` to `width=output_size[0], height=output_size[1]`. The pipeline uses separate width and height parameters, not a combined size parameter.

## Related Documentation

- WAN2.2 Model: https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B-Diffusers
- Plan file: /home/ytjohn/.claude/plans/bright-splashing-rabin.md

## Summary of Benefits

✓ **User control**: Choose speed (480p) vs quality (720p)
✓ **Auto-detection**: Aspect ratio handled automatically
✓ **Better quality**: Native 720p support for sharper videos
✓ **Backward compatible**: Existing workflows unchanged
✓ **Preset integration**: Presets include sensible resolution defaults
✓ **Metadata tracking**: Resolution saved with each run for reproducibility
