#!/usr/bin/env python3
"""Monitor benchmark progress and update bd issue with findings."""

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path


def get_latest_log():
    """Find the most recent worker log file."""
    log_locations = [
        Path("outputs/logs"),
        Path("tmp"),
        Path("/tmp"),
    ]

    log_files = []
    for loc in log_locations:
        if loc.exists():
            log_files.extend(loc.glob("*worker*.log"))

    if not log_files:
        return None

    return max(log_files, key=lambda p: p.stat().st_mtime)


def analyze_benchmark_results():
    """Check if benchmark results exist and analyze them."""
    result_file = Path("benchmark_output/benchmark_results.json")
    if not result_file.exists():
        return None

    with open(result_file) as f:
        data = json.load(f)

    if not data.get("results"):
        return None

    results = data["results"]
    video_results = [r for r in results if r.get("type") == "video"]

    if not video_results:
        return None

    total_in_batch = data.get("total", len(video_results))
    completed = data.get("completed", len(video_results))

    analysis = {
        "total_videos": total_in_batch,
        "completed": completed,
        "failed": 0,  # Will need to check logs for failures
        "times": []
    }

    # Analyze time per step for progressive slowdown
    for i, result in enumerate(video_results, 1):
        # Results in array are assumed successful
        time_per_step = result.get("time_per_step")
        if time_per_step is None and result.get("seconds_elapsed") and result.get("steps"):
            time_per_step = result["seconds_elapsed"] / result["steps"]

        if time_per_step:
            analysis["times"].append({
                "video_num": i,
                "time_per_step": time_per_step,
                "total_time": result.get("seconds_elapsed", 0),
                "steps": result.get("steps", result.get("num_inference_steps", 0))
            })

    return analysis


def check_log_for_issues(log_path):
    """Scan log for GPU errors, cleanup messages, and other issues."""
    if not log_path or not log_path.exists():
        return {"error": "Log file not found"}

    issues = {
        "hip_errors": 0,
        "cleanup_messages": 0,
        "gpu_hangs": 0,
        "recent_lines": []
    }

    # Read last 100 lines
    try:
        result = subprocess.run(
            ["tail", "-n", "100", str(log_path)],
            capture_output=True,
            text=True,
            timeout=5
        )
        lines = result.stdout.split("\n")

        for line in lines[-20:]:
            if line.strip():
                issues["recent_lines"].append(line)

        for line in lines:
            if "HIP error" in line or "hipError" in line:
                issues["hip_errors"] += 1
            if "GPU cleanup" in line or "Freeing GPU memory" in line:
                issues["cleanup_messages"] += 1
            if "hang" in line.lower() or "unspecified launch failure" in line:
                issues["gpu_hangs"] += 1

    except Exception as e:
        issues["error"] = str(e)

    return issues


def format_update(analysis, log_issues):
    """Format findings for bd issue update."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    update = f"\n\n## Monitoring Update - {timestamp}\n\n"

    if analysis:
        update += f"**Benchmark Progress:**\n"
        update += f"- Videos completed: {analysis['completed']}/{analysis['total_videos']}\n"
        update += f"- Videos failed: {analysis['failed']}\n\n"

        if analysis['times']:
            update += "**Time per step analysis:**\n"
            for t in analysis['times'][-5:]:  # Last 5 videos
                update += f"- Video {t['video_num']}: {t['time_per_step']:.2f}s/step ({t['total_time']:.1f}s total, {t['steps']} steps)\n"

            # Check for progressive slowdown
            if len(analysis['times']) >= 3:
                first_avg = sum(t['time_per_step'] for t in analysis['times'][:2]) / 2
                last_avg = sum(t['time_per_step'] for t in analysis['times'][-2:]) / 2
                ratio = last_avg / first_avg

                update += f"\n**Slowdown ratio:** {ratio:.2f}x"
                if ratio > 1.5:
                    update += " ⚠️ **PROGRESSIVE SLOWDOWN DETECTED**"
                elif ratio < 1.2:
                    update += " ✓ No significant slowdown"
                update += "\n"
    else:
        update += "**Benchmark Progress:** No results file yet or benchmark still initializing\n"

    update += f"\n**Log Analysis:**\n"
    if "error" in log_issues:
        update += f"- Error checking logs: {log_issues['error']}\n"
    else:
        update += f"- HIP errors: {log_issues['hip_errors']}\n"
        update += f"- GPU cleanup messages: {log_issues['cleanup_messages']}\n"
        update += f"- GPU hang indicators: {log_issues['gpu_hangs']}\n"

        if log_issues['hip_errors'] > 0:
            update += "\n⚠️ **HIP ERRORS DETECTED** - GPU may be having issues\n"

        if log_issues['cleanup_messages'] > 0:
            update += "\n✓ GPU cleanup is running\n"

    if log_issues.get('recent_lines'):
        update += f"\n**Recent log tail:**\n```\n"
        for line in log_issues['recent_lines'][-5:]:
            update += f"{line}\n"
        update += "```\n"

    return update


def update_issue(update_text):
    """Append update to issue notes."""
    try:
        # Get current issue
        result = subprocess.run(
            ["bd", "show", "mydiffuser-8se", "--json"],
            capture_output=True,
            text=True,
            timeout=10
        )

        issue_data = json.loads(result.stdout)[0]
        current_notes = issue_data.get("notes", "")

        # Append new update
        new_notes = current_notes + update_text

        # Update issue with new notes
        subprocess.run(
            ["bd", "update", "mydiffuser-8se", "--notes", new_notes],
            timeout=10,
            check=True
        )

        print(f"✓ Updated mydiffuser-8se at {datetime.now().strftime('%H:%M:%S')}")
        return True

    except Exception as e:
        print(f"✗ Failed to update issue: {e}")
        return False


def main():
    """Main monitoring loop."""
    print("Starting benchmark monitor...")
    print("Will check every 10 minutes and update mydiffuser-8se")
    print("Press Ctrl+C to stop")

    iteration = 0

    try:
        while True:
            iteration += 1
            print(f"\n{'='*60}")
            print(f"Check #{iteration} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print('='*60)

            # Find log file
            log_path = get_latest_log()
            if log_path:
                print(f"Log file: {log_path}")
            else:
                print("No log file found")

            # Analyze benchmark results
            analysis = analyze_benchmark_results()
            if analysis:
                print(f"Benchmark: {analysis['completed']}/{analysis['total_videos']} videos complete")
            else:
                print("Benchmark: No results yet")

            # Check logs
            log_issues = check_log_for_issues(log_path)
            if log_issues.get('hip_errors', 0) > 0:
                print(f"⚠️  Found {log_issues['hip_errors']} HIP errors in recent logs")

            # Format and update issue
            update_text = format_update(analysis, log_issues)
            update_issue(update_text)

            # Sleep for 10 minutes
            print("\nSleeping for 10 minutes...")
            time.sleep(600)  # 10 minutes

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user")
    except Exception as e:
        print(f"\n\nMonitoring stopped due to error: {e}")


if __name__ == "__main__":
    main()
