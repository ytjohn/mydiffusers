#!/bin/bash
# Terminate all Lambda Labs instances
#
# Usage:
#   LAMBDA_API_KEY=xxx ./lambda-killall.sh [--yes]
#
# Options:
#   --yes    Skip confirmation prompt
#
# Environment:
#   LAMBDA_API_KEY    Required: Lambda Labs API key

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source the library
source "$SCRIPT_DIR/lambda-lib.sh"

# Configuration
SKIP_CONFIRM=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --yes|-y)
            SKIP_CONFIRM=true
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

echo -e "${YELLOW}=== Lambda Labs Instance Terminator ===${NC}"
echo ""

# Get all instances
echo -e "${BLUE}Fetching all instances...${NC}"
instances_data=$(get_instances)

# Filter for active/booting instances
instance_ids=$(echo "$instances_data" | jq -r '.data[] | select(.status != "terminated") | .id' 2>/dev/null || true)

if [[ -z "$instance_ids" ]]; then
    echo -e "${GREEN}No instances found to terminate${NC}"
    exit 0
fi

# Count instances
instance_count=$(echo "$instance_ids" | wc -l)

echo -e "${YELLOW}Found $instance_count instance(s) to terminate:${NC}"
echo ""

# Show instance details
echo "$instances_data" | jq -r '.data[] | select(.status != "terminated") | "  \(.id) - \(.name) (\(.instance_type.name)) - \(.status) - \(.region.name)"'

echo ""

# Confirmation prompt
if [[ "$SKIP_CONFIRM" != "true" ]]; then
    echo -e "${RED}⚠️  This will terminate ALL instances listed above${NC}"
    read -p "Are you sure? (yes/no): " confirm

    if [[ "$confirm" != "yes" ]]; then
        echo -e "${YELLOW}Aborted${NC}"
        exit 0
    fi
fi

# Terminate instances
echo ""
echo -e "${YELLOW}Terminating instances...${NC}"

# Convert to array
mapfile -t ids_array <<< "$instance_ids"

# Terminate
result=$(terminate_instances "${ids_array[@]}")

# Check result
if echo "$result" | jq -e '.error' > /dev/null 2>&1; then
    echo -e "${RED}Termination failed:${NC}"
    echo "$result" | jq '.error'
    exit 1
fi

# Show results
terminated_count=$(echo "$result" | jq -r '.data.terminated_instances | length')

echo -e "${GREEN}Successfully terminated $terminated_count instance(s)${NC}"
echo ""

# Show terminated instances
echo "$result" | jq -r '.data.terminated_instances[] | "  \(.id) - \(.name) - terminated"'

echo ""
echo -e "${GREEN}✓ All instances terminated${NC}"
