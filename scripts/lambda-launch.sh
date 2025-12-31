#!/bin/bash
# Launch Lambda Labs instance and deploy MyDiffuser worker
#
# Usage:
#   LAMBDA_API_KEY=xxx ./lambda-launch.sh [--force]
#
# Options:
#   --force    Launch new instance even if one is already running
#
# Environment:
#   LAMBDA_API_KEY              Required: Lambda Labs API key
#   LAMBDA_PREFERRED_TYPES      Optional: Space-separated instance types (default: "gpu_1x_gh200 gpu_1x_h100_pcie gpu_1x_a100 gpu_1x_a10")
#   LAMBDA_LOCAL_PORT           Optional: Local SSH tunnel port (default: 8002)
#   LAMBDA_WORKER_PORT          Optional: Remote worker port (default: 8001)

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Source the library
source "$SCRIPT_DIR/lambda-lib.sh"

# Configuration
FORCE_LAUNCH=false
# gpu_1x_gh200 = Lambda's new GPU instance with GH200 GPUs, cheapest and most memory
PREFERRED_TYPES="${LAMBDA_PREFERRED_TYPES:-gpu_1x_gh200 gpu_1x_h100_pcie gpu_1x_a100 gpu_1x_a10}"
LOCAL_PORT="${LAMBDA_LOCAL_PORT:-8002}"
WORKER_PORT="${LAMBDA_WORKER_PORT:-8001}"
INSTANCE_NAME="mydiffuser-worker"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE_LAUNCH=true
            shift
            ;;
        --help|-h)
            grep "^#" "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check prerequisites
check_api_key

if ! command -v jq &> /dev/null; then
    echo -e "${RED}Error: jq is required but not installed${NC}" >&2
    echo "Install with: sudo apt-get install jq" >&2
    exit 1
fi

echo -e "${GREEN}=== Lambda Labs Instance Manager ===${NC}"
echo ""

# Step 1: Check for existing instances
echo -e "${BLUE}Step 1: Checking for existing instances...${NC}"
instances_data=$(get_instances)
existing_instances=$(echo "$instances_data" | jq -r '.data[] | select(.status == "active" or .status == "booting") | .id' 2>/dev/null || true)

if [[ -n "$existing_instances" ]] && [[ "$FORCE_LAUNCH" != "true" ]]; then
    echo -e "${YELLOW}Found existing instance(s):${NC}"
    echo "$instances_data" | jq -r '.data[] | select(.status == "active" or .status == "booting") | "  \(.id) - \(.name) (\(.instance_type.name)) - \(.status)"'

    # Get first active instance
    instance_id=$(echo "$existing_instances" | head -n1)
    instance_data=$(get_instance "$instance_id")

    echo ""
    print_instance_info "$instance_data"
    echo ""
    echo -e "${GREEN}Using existing instance. To launch a new one, use: $0 --force${NC}"

    # Extract IP for SSH tunnel
    instance_ip=$(echo "$instance_data" | jq -r '.data.ip')

    # Skip to SSH tunnel setup
    echo ""
    echo -e "${BLUE}Step 5: Setting up SSH tunnel...${NC}"
    echo -e "${GREEN}Run this command to create SSH tunnel:${NC}"
    echo ""
    echo -e "  ${YELLOW}ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -N -L ${LOCAL_PORT}:localhost:${WORKER_PORT} ubuntu@${instance_ip}${NC}"
    echo ""
    echo -e "${GREEN}Then configure client with:${NC}"
    echo -e "  export MYDIFFUSER_REMOTE_WORKER=\"http://localhost:${LOCAL_PORT}\""
    echo ""
    echo -e "${GREEN}Test with:${NC}"
    echo -e "  curl http://localhost:${LOCAL_PORT}/health | jq"

    exit 0
fi

# Step 2: Find SSH key
echo -e "${BLUE}Step 2: Finding SSH key...${NC}"
ssh_key_name=$(get_first_ssh_key)
if [[ -z "$ssh_key_name" ]]; then
    exit 1
fi
echo -e "${GREEN}Using SSH key: $ssh_key_name${NC}"

# Step 3: Find available instance and region
echo -e "${BLUE}Step 3: Finding available instance type and region...${NC}"
selected_type=""
selected_region=""

for instance_type in $PREFERRED_TYPES; do
    echo -e "${BLUE}Trying $instance_type...${NC}"

    if region=$(find_available_region "$instance_type"); then
        selected_type="$instance_type"
        selected_region="$region"
        echo -e "${GREEN}✓ Found capacity: $instance_type in $region${NC}"
        break
    else
        echo -e "${YELLOW}✗ No capacity for $instance_type${NC}"
    fi
done

if [[ -z "$selected_type" ]]; then
    echo -e "${RED}No capacity available for any preferred instance type${NC}" >&2
    echo -e "${YELLOW}Tried: $PREFERRED_TYPES${NC}" >&2
    exit 1
fi

# Step 4: Launch instance
echo ""
echo -e "${BLUE}Step 4: Launching instance...${NC}"
echo -e "  Type:   $selected_type"
echo -e "  Region: $selected_region"
echo -e "  Key:    $ssh_key_name"
echo ""

launch_result=$(launch_instance "$selected_region" "$selected_type" "$ssh_key_name" "$INSTANCE_NAME")

# Check for errors
if echo "$launch_result" | jq -e '.error' > /dev/null 2>&1; then
    echo -e "${RED}Launch failed:${NC}"
    echo "$launch_result" | jq '.error'
    exit 1
fi

instance_id=$(echo "$launch_result" | jq -r '.data.instance_ids[0]')

if [[ -z "$instance_id" ]] || [[ "$instance_id" == "null" ]]; then
    echo -e "${RED}Failed to get instance ID from launch response${NC}"
    echo "$launch_result" | jq
    exit 1
fi

echo -e "${GREEN}Instance launched: $instance_id${NC}"

# Wait for instance to be active
echo ""
echo -e "${BLUE}Waiting for instance to boot (this takes ~5 minutes)...${NC}"
if ! instance_data=$(wait_for_instance "$instance_id"); then
    echo -e "${RED}Instance failed to become active${NC}"
    exit 1
fi

echo ""
print_instance_info "$instance_data"

# Extract connection details
instance_ip=$(echo "$instance_data" | jq -r '.data.ip')

# Step 5: Deploy worker
echo ""
echo -e "${BLUE}Step 5: Deploying worker to instance...${NC}"

# Give SSH a moment to be fully ready
echo "Waiting 30s for SSH to be fully ready..."
sleep 30

# Run deploy script
if [[ -f "$SCRIPT_DIR/deploy-worker.sh" ]]; then
    echo -e "${GREEN}Running deploy-worker.sh...${NC}"

    # Call deploy-worker.sh with the instance IP
    # Assuming deploy-worker.sh accepts hostname as first argument
    export REMOTE_HOST="ubuntu@${instance_ip}"
    bash "$SCRIPT_DIR/deploy-worker.sh" "$instance_ip" || {
        echo -e "${RED}Warning: deploy-worker.sh failed, but instance is running${NC}"
        echo -e "${YELLOW}You can manually deploy with: bash $SCRIPT_DIR/deploy-worker.sh $instance_ip${NC}"
    }
else
    echo -e "${YELLOW}Warning: deploy-worker.sh not found${NC}"
    echo -e "${YELLOW}Manual deployment instructions:${NC}"
    echo ""
    echo "  1. SSH to instance: ssh ubuntu@${instance_ip}"
    echo "  2. Clone repo and install dependencies"
    echo "  3. Start worker: python scripts/run_worker.py --port ${WORKER_PORT}"
fi

# Step 6: SSH tunnel instructions
echo ""
echo -e "${GREEN}=== Setup Complete ===${NC}"
echo ""
echo -e "${BLUE}Step 6: Setting up SSH tunnel...${NC}"
echo -e "${GREEN}Run this command in a separate terminal:${NC}"
echo ""
echo -e "  ${YELLOW}ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -N -L ${LOCAL_PORT}:localhost:${WORKER_PORT} ubuntu@${instance_ip}${NC}"
echo ""
echo -e "${GREEN}Then configure client with:${NC}"
echo -e "  export MYDIFFUSER_REMOTE_WORKER=\"http://localhost:${LOCAL_PORT}\""
echo ""
echo -e "${GREEN}Test worker connection:${NC}"
echo -e "  curl http://localhost:${LOCAL_PORT}/health | jq"
echo ""
echo -e "${BLUE}Instance Details:${NC}"
echo -e "  ID:  ${instance_id}"
echo -e "  IP:  ${instance_ip}"
echo -e "  SSH: ssh ubuntu@${instance_ip}"
echo ""
echo -e "${YELLOW}Don't forget to terminate when done:${NC}"
echo -e "  bash $SCRIPT_DIR/lambda-killall.sh"
echo ""
