#!/usr/bin/env python3
"""
Test the new estimation API and database integration
"""

import json
import requests


# Test the estimation API
def test_estimation_api():
    """Test the new estimation endpoint"""

    # Test data
    test_cases = [
        {
            "type": "image",
            "model_id": "Tongyi-MAI/Z-Image-Turbo",
            "parameters": {
                "width": 1920,
                "height": 1080,
                "num_inference_steps": 30,
                "guidance_scale": 5.0,
                "dtype": "float16",
            },
            "worker_id": "local",
        },
        {
            "type": "video",
            "model_id": "Wan-AI/Wan2.2-TI2V-5B-Diffusers",
            "parameters": {
                "width": 1280,
                "height": 704,
                "num_frames": 60,
                "num_inference_steps": 20,
                "guidance_scale": 3.0,
                "dtype": "float16",
            },
            "worker_id": "local",
        },
    ]

    print("🧪 Testing Estimation API")
    print("=" * 50)

    for test_case in test_cases:
        print(f"\n📊 {test_case['type'].upper()} Estimation:")
        print(f"   Model: {test_case['model_id']}")
        print(f"   Worker: {test_case['worker_id']}")

        try:
            # This would work with a running server
            # response = requests.post("http://localhost:8000/api/estimate", json=test_case)
            # result = response.json()

            # For now, let's test the estimator directly
            from mydiffuser.client.estimate import job_estimator

            estimate = job_estimator.estimate_job(
                test_case["type"],
                test_case["model_id"],
                test_case["parameters"],
                test_case["worker_id"],
            )

            print(f"   📈 VRAM Needed: {estimate.vram_total_needed:.1f} GB")
            print(f"   🕒 Time Estimate: {estimate.time_estimate_seconds:.0f} seconds")
            print(f"   ✅ Available: {estimate.worker_available}")
            print(f"   📦 Model Loaded: {estimate.model_loaded}")

        except Exception as e:
            print(f"   ❌ Error: {e}")


if __name__ == "__main__":
    test_estimation_api()
