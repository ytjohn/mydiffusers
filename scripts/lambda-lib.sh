#!/bin/bash
# Lambda Labs Cloud API Library
# Common functions for managing Lambda instances

# Configuration
LAMBDA_API_BASE="https://cloud.lambda.ai/api/v1"
LAMBDA_API_KEY="${LAMBDA_API_KEY:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Error handling
set -o pipefail

# Check if API key is set
check_api_key() {
    if [[ -z "$LAMBDA_API_KEY" ]]; then
        echo -e "${RED}Error: LAMBDA_API_KEY environment variable not set${NC}" >&2
        echo "Get your API key from: https://cloud.lambda.ai/api-keys" >&2
        echo "Then run: export LAMBDA_API_KEY='your-key-here'" >&2
        exit 1
    fi
}

# Make authenticated API request
# Usage: api_request METHOD PATH [DATA]
api_request() {
    local method="$1"
    local path="$2"
    local data="${3:-}"

    check_api_key

    local url="${LAMBDA_API_BASE}${path}"
    local args=(-s -X "$method" -u "${LAMBDA_API_KEY}:")

    if [[ -n "$data" ]]; then
        args+=(-H "Content-Type: application/json" -d "$data")
    fi

    curl "${args[@]}" "$url"
}

# Get all running instances
# Returns: JSON array of instances
get_instances() {
    api_request GET "/instances"
}

# Get instance types with availability
# Returns: JSON object of instance types
get_instance_types() {
    api_request GET "/instance-types"
}

# Launch instance
# Usage: launch_instance REGION INSTANCE_TYPE SSH_KEY_NAME [NAME]
launch_instance() {
    local region="$1"
    local instance_type="$2"
    local ssh_key="$3"
    local name="${4:-mydiffuser-worker}"

    local data=$(cat <<EOF
{
    "region_name": "$region",
    "instance_type_name": "$instance_type",
    "ssh_key_names": ["$ssh_key"],
    "name": "$name"
}
EOF
)

    echo -e "${BLUE}Launching $instance_type in $region...${NC}" >&2
    api_request POST "/instance-operations/launch" "$data"
}

# Terminate instances
# Usage: terminate_instances INSTANCE_ID1 [INSTANCE_ID2 ...]
terminate_instances() {
    local instance_ids=("$@")

    # Build JSON array
    local ids_json=$(printf '"%s",' "${instance_ids[@]}")
    ids_json="[${ids_json%,}]"

    local data="{\"instance_ids\": $ids_json}"

    echo -e "${YELLOW}Terminating instances: ${instance_ids[*]}${NC}" >&2
    api_request POST "/instance-operations/terminate" "$data"
}

# Get instance details
# Usage: get_instance INSTANCE_ID
get_instance() {
    local instance_id="$1"
    api_request GET "/instances/$instance_id"
}

# Get SSH keys
get_ssh_keys() {
    api_request GET "/ssh-keys"
}

# Wait for instance to be active
# Usage: wait_for_instance INSTANCE_ID [MAX_ATTEMPTS]
wait_for_instance() {
    local instance_id="$1"
    local max_attempts="${2:-60}"  # 60 attempts = 5 minutes (5s intervals)
    local attempt=0

    echo -e "${BLUE}Waiting for instance $instance_id to become active...${NC}" >&2

    while ((attempt < max_attempts)); do
        local instance_data=$(get_instance "$instance_id")
        local status=$(echo "$instance_data" | jq -r '.data.status // empty')

        if [[ "$status" == "active" ]]; then
            echo -e "${GREEN}Instance is active!${NC}" >&2
            echo "$instance_data"
            return 0
        elif [[ "$status" == "unhealthy" ]] || [[ "$status" == "terminated" ]]; then
            echo -e "${RED}Instance entered unhealthy/terminated state: $status${NC}" >&2
            return 1
        fi

        echo -e "${YELLOW}Status: $status (attempt $((attempt + 1))/$max_attempts)${NC}" >&2
        sleep 5
        ((attempt++))
    done

    echo -e "${RED}Timeout waiting for instance to become active${NC}" >&2
    return 1
}

# Find available region for instance type
# Usage: find_available_region INSTANCE_TYPE
# Returns the first available region with capacity
find_available_region() {
    local instance_type="$1"

    echo -e "${BLUE}Checking availability for $instance_type...${NC}" >&2

    local types_data=$(get_instance_types)
    local available_regions=$(echo "$types_data" | jq -r ".data.\"$instance_type\".regions_with_capacity_available[].name // empty")

    if [[ -z "$available_regions" ]]; then
        echo -e "${RED}No capacity available for $instance_type${NC}" >&2
        return 1
    fi

    echo -e "${GREEN}Available regions: $(echo $available_regions | tr '\n' ' ')${NC}" >&2

    # Return first available region
    local first_region=$(echo "$available_regions" | head -n1)
    echo "$first_region"
    return 0
}

# Get SSH key name (first available)
get_first_ssh_key() {
    local keys_data=$(get_ssh_keys)
    local key_name=$(echo "$keys_data" | jq -r '.data[0].name // empty')

    if [[ -z "$key_name" ]]; then
        echo -e "${RED}No SSH keys found. Please add one at: https://cloud.lambda.ai/ssh-keys${NC}" >&2
        return 1
    fi

    echo "$key_name"
}

# Pretty print instance info
print_instance_info() {
    local instance_data="$1"

    local id=$(echo "$instance_data" | jq -r '.data.id')
    local name=$(echo "$instance_data" | jq -r '.data.name')
    local status=$(echo "$instance_data" | jq -r '.data.status')
    local type=$(echo "$instance_data" | jq -r '.data.instance_type.name')
    local region=$(echo "$instance_data" | jq -r '.data.region.name')
    local ip=$(echo "$instance_data" | jq -r '.data.ip')

    echo -e "${GREEN}Instance Details:${NC}"
    echo -e "  ID:     $id"
    echo -e "  Name:   $name"
    echo -e "  Status: $status"
    echo -e "  Type:   $type"
    echo -e "  Region: $region"
    echo -e "  IP:     $ip"
}

# Export functions for use in other scripts
export -f check_api_key api_request get_instances get_instance_types
export -f launch_instance terminate_instances get_instance get_ssh_keys
export -f wait_for_instance find_available_region get_first_ssh_key
export -f print_instance_info
