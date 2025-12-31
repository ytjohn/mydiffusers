#!/bin/bash
# List all Lambda Labs instances
#
# Usage:
#   LAMBDA_API_KEY=xxx ./lambda-list.sh [--json]
#
# Options:
#   --json     Output raw JSON instead of formatted table
#
# Environment:
#   LAMBDA_API_KEY    Required: Lambda Labs API key

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source the library
source "$SCRIPT_DIR/lambda-lib.sh"

# Configuration
OUTPUT_JSON=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --json)
            OUTPUT_JSON=true
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

# Get instances
instances_data=$(get_instances)

# Check for errors
if echo "$instances_data" | jq -e '.error' > /dev/null 2>&1; then
    echo -e "${RED}Failed to list instances:${NC}" >&2
    echo "$instances_data" | jq '.error' >&2
    exit 1
fi

# Output raw JSON if requested
if [[ "$OUTPUT_JSON" == "true" ]]; then
    echo "$instances_data" | jq
    exit 0
fi

# Count instances
instance_count=$(echo "$instances_data" | jq '.data | length')

echo -e "${GREEN}=== Lambda Labs Instances ===${NC}"
echo ""

if [[ "$instance_count" -eq 0 ]]; then
    echo -e "${YELLOW}No instances found${NC}"
    exit 0
fi

# Print formatted table header
printf "%-20s %-25s %-20s %-15s %-15s %s\n" "ID" "NAME" "TYPE" "REGION" "STATUS" "IP"
printf "%-20s %-25s %-20s %-15s %-15s %s\n" "----" "----" "----" "------" "------" "--"

# Print each instance
echo "$instances_data" | jq -r '.data[] |
    [
        .id[0:20],
        .name,
        .instance_type.name,
        .region.name,
        .status,
        (.ip // "N/A")
    ] | @tsv' | \
while IFS=$'\t' read -r id name type region status ip; do
    # Color code status
    case "$status" in
        active)
            status_colored="${GREEN}${status}${NC}"
            ;;
        booting)
            status_colored="${YELLOW}${status}${NC}"
            ;;
        unhealthy|terminated)
            status_colored="${RED}${status}${NC}"
            ;;
        *)
            status_colored="$status"
            ;;
    esac

    printf "%-20s %-25s %-20s %-15s %-15b %s\n" \
        "$id" "$name" "$type" "$region" "$status_colored" "$ip"
done

echo ""
echo -e "${BLUE}Total instances: $instance_count${NC}"
echo ""
echo -e "${YELLOW}Tip: Use --json flag for raw JSON output${NC}"
echo -e "${YELLOW}Tip: Terminate all instances with: ./lambda-killall.sh${NC}"
