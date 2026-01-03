# Lambda Labs Instance Management

Automated scripts for managing Lambda Labs GPU instances for MyDiffuser workers.

## Overview

The Lambda management scripts provide automated control over Lambda Labs cloud GPU instances:

- **`lambda-launch.sh`** - Smart launcher that checks for existing instances, launches new ones with preferred GPU types, deploys the worker, and sets up SSH tunnels
- **`lambda-killall.sh`** - Safely terminates all running instances
- **`lambda-lib.sh`** - Shared library with Lambda API functions (used by other scripts)

## Prerequisites

1. **Lambda Labs Account**
   - Sign up at https://cloud.lambda.ai/
   - Add credit to your account
   - Add an SSH key at https://cloud.lambda.ai/ssh-keys

2. **API Key**
   - Generate at https://cloud.lambda.ai/api-keys
   - Keep this secret!

3. **Required Tools**
   - `curl` - For API requests
   - `jq` - For JSON parsing
   - `ssh` - For SSH tunnels

## Setup

### 1. Configure Environment

```bash
# Copy example environment file
cp .env.lambda.example .env.lambda

# Edit with your API key
nano .env.lambda

# Load environment variables
source .env.lambda
```

### 2. Verify Configuration

```bash
# Test API connection
curl -s -u "$LAMBDA_API_KEY:" https://cloud.lambda.ai/api/v1/instances | jq
```

## Usage

### Launch Instance

The launch script will:
1. Check if an instance is already running (avoids duplicates)
2. Find an available GPU from your preferred types
3. Launch the instance in the first available region
4. Wait for instance to boot (~5 minutes)
5. Deploy the MyDiffuser worker (if `deploy-worker.sh` exists)
6. Show SSH tunnel command

**Basic launch:**
```bash
source .env.lambda
bash scripts/lambda-launch.sh
```

**Force new instance (even if one exists):**
```bash
bash scripts/lambda-launch.sh --force
```

**Custom instance preferences:**
```bash
# Override preferred instance types
LAMBDA_PREFERRED_TYPES="gpu_1x_h100_pcie gpu_1x_a100" bash scripts/lambda-launch.sh

# Override preferred regions
LAMBDA_PREFERRED_REGIONS="us-west-1 us-east-1" bash scripts/lambda-launch.sh
```

### SSH Tunnel

After launch, create an SSH tunnel to access the worker:

```bash
# Command shown by lambda-launch.sh:
ssh -N -L 8002:localhost:8001 ubuntu@<instance-ip>
```

**In a separate terminal**, configure the client:
```bash
export MYDIFFUSER_REMOTE_WORKER="http://localhost:8002"
curl http://localhost:8002/health | jq
```

### Terminate Instances

**Interactive (with confirmation):**
```bash
bash scripts/lambda-killall.sh
```

**Non-interactive (skip confirmation):**
```bash
bash scripts/lambda-killall.sh --yes
```

## Configuration Options

All options can be set via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LAMBDA_API_KEY` | *(required)* | Lambda Labs API key |
| `LAMBDA_PREFERRED_TYPES` | `gpu_1x_h100_pcie gpu_1x_a100 gpu_1x_a10` | Space-separated instance types in priority order |
| `LAMBDA_PREFERRED_REGIONS` | `us-west-1 us-east-1 us-west-2 us-south-1` | Space-separated regions in priority order |
| `LAMBDA_LOCAL_PORT` | `8002` | Local port for SSH tunnel |
| `LAMBDA_WORKER_PORT` | `8001` | Remote worker port on instance |

## Instance Types

Common Lambda Labs instance types:

| Type | GPU | VRAM | Use Case | Cost (approx) |
|------|-----|------|----------|---------------|
| `gpu_1x_a10` | A10 (24GB) | 24GB | Testing, 5B models | ~$0.60/hr |
| `gpu_1x_a100` | A100 (40GB) | 40GB | 5B/14B models | ~$1.10/hr |
| `gpu_1x_h100_pcie` | H100 PCIe (80GB) | 80GB | Best performance | ~$2.00/hr |
| `gpu_1x_a100_sxm4` | A100 SXM4 (40GB) | 40GB | High bandwidth | ~$1.29/hr |

See full list: https://cloud.lambda.ai/instance-types

## Regions

Available regions (check capacity at https://cloud.lambda.ai/):

- `us-west-1` - California
- `us-west-2` - California (alternative)
- `us-east-1` - Virginia
- `us-south-1` - Texas
- `us-midwest-1` - Illinois
- `europe-central-1` - Germany
- `asia-south-1` - India
- `asia-northeast-1` - Japan
- `asia-northeast-2` - South Korea

## Workflow Examples

### Standard Workflow

```bash
# 1. Launch instance
source .env.lambda
bash scripts/lambda-launch.sh

# 2. Wait for deployment (~5 minutes)
# Script will show progress

# 3. Open SSH tunnel (in separate terminal)
ssh -N -L 8002:localhost:8001 ubuntu@<ip>

# 4. Configure and test client
export MYDIFFUSER_REMOTE_WORKER="http://localhost:8002"
curl http://localhost:8002/health | jq

# 5. Use the worker via client UI
# Visit http://localhost:8000 and select "remote" worker

# 6. When done, terminate instance
bash scripts/lambda-killall.sh --yes
```

### Multiple Sessions

```bash
# Check for existing instance first
bash scripts/lambda-launch.sh
# Output: "Using existing instance..."

# Reconnect SSH tunnel
ssh -N -L 8002:localhost:8001 ubuntu@<ip>

# Continue working
```

### Different GPU for Testing

```bash
# Quick test on cheaper A10
LAMBDA_PREFERRED_TYPES="gpu_1x_a10" bash scripts/lambda-launch.sh
```

## Troubleshooting

### "No capacity available"

Lambda capacity varies. Try:
1. Different instance types (add more to `LAMBDA_PREFERRED_TYPES`)
2. Different regions (add more to `LAMBDA_PREFERRED_REGIONS`)
3. Wait and retry (capacity changes frequently)

### "No SSH keys found"

Add an SSH key at: https://cloud.lambda.ai/ssh-keys

### "Connection refused" on SSH tunnel

- Wait longer (instance may still be booting)
- Check worker is running: `ssh ubuntu@<ip> "ps aux | grep python"`
- Check worker logs: `ssh ubuntu@<ip> "screen -r worker"`

### Instance stuck "booting"

- Lambda occasionally has boot issues
- Terminate and launch again: `bash scripts/lambda-killall.sh --yes && bash scripts/lambda-launch.sh`

### API Rate Limiting

Lambda API limits:
- Launch: 5 requests/minute
- Other operations: Higher limits

If rate-limited, wait 60 seconds and retry.

## Cost Management

**Important**: You are charged by the hour (prorated by the second after the first minute).

- Always terminate instances when done: `bash scripts/lambda-killall.sh --yes`
- Set billing alerts in Lambda dashboard
- Check running instances: `curl -s -u "$LAMBDA_API_KEY:" https://cloud.lambda.ai/api/v1/instances | jq '.data[] | {id, name, status}'`

**Cost estimates (as of 2025):**
- A10: ~$0.60/hr
- A100: ~$1.10/hr
- H100: ~$2.00/hr

## Advanced Usage

### Using Lambda API Directly

All scripts use `lambda-lib.sh` functions. You can source the library for manual API calls:

```bash
source scripts/lambda-lib.sh

# List instances
get_instances | jq

# Get instance types
get_instance_types | jq

# Launch custom instance
launch_instance "us-west-1" "gpu_1x_a100" "my-ssh-key" "my-instance-name"

# Terminate specific instance
terminate_instances "instance-id-here"
```

### Integration with CI/CD

```bash
#!/bin/bash
# Example: Launch, test, terminate

set -e

# Launch instance
source .env.lambda
output=$(bash scripts/lambda-launch.sh)
instance_ip=$(echo "$output" | grep -oP 'IP:\s+\K[0-9.]+')

# Setup tunnel in background
ssh -f -N -L 8002:localhost:8001 ubuntu@$instance_ip

# Run tests
export MYDIFFUSER_REMOTE_WORKER="http://localhost:8002"
pytest tests/test_worker.py

# Cleanup
bash scripts/lambda-killall.sh --yes
```

## API Reference

See official Lambda Labs API docs: https://docs-api.lambda.ai/api/cloud

Key endpoints used by scripts:
- `GET /instance-types` - List available GPUs
- `GET /instances` - List running instances
- `POST /instance-operations/launch` - Launch instance
- `POST /instance-operations/terminate` - Terminate instances
- `GET /ssh-keys` - List SSH keys

## Security

- **Never commit `.env.lambda`** - It contains your API key (already in `.gitignore`)
- **Rotate API keys regularly** - Generate new keys at https://cloud.lambda.ai/api-keys
- **Use SSH key authentication** - Never use passwords for SSH
- **Firewall rules** - Lambda defaults are secure (no external access to worker port)
- **SSH tunnels** - All worker traffic encrypted via SSH

## Related Documentation

- [CLIENT_WORKER_STATUS.md](CLIENT_WORKER_STATUS.md) - Client/Worker architecture
- [agents.md](agents.md) - Project overview
- [deploy-worker.sh](scripts/deploy-worker.sh) - Manual deployment script

## Support

Lambda Labs support: https://support.lambdalabs.com/

Common issues:
- Billing: Check dashboard at https://cloud.lambda.ai/billing
- Quota limits: Request increase via support
- GPU availability: Check https://cloud.lambda.ai/instances for real-time capacity
