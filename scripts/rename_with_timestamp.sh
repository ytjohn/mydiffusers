#!/bin/bash
# Script to rename image output directories with timestamp prefix
# This prepends the creation timestamp (YYYYMMDD-HHMMSS) to directory names
# making them easier to browse by date

IMAGE_DIR="${1:-/home/ytjohn/projects/mydiffuser/outputs/run/image}"

if [ ! -d "$IMAGE_DIR" ]; then
    echo "Error: Directory '$IMAGE_DIR' does not exist"
    exit 1
fi

cd "$IMAGE_DIR"

# Counter for tracking renames
renamed=0
skipped=0

for dir in */; do
    # Remove trailing slash
    dirname="${dir%/}"
    
    # Skip if already has timestamp prefix (YYYYMMDD-HHMMSS_)
    if [[ "$dirname" =~ ^[0-9]{8}-[0-9]{6}_ ]]; then
        echo "Skipping (already has timestamp): $dirname"
        ((skipped++))
        continue
    fi
    
    # Get birth time (creation time) using stat
    # Fall back to modification time if birth time isn't available
    birthtime=$(stat -c %W "$dirname" 2>/dev/null)
    
    if [ "$birthtime" = "0" ] || [ -z "$birthtime" ]; then
        # Birth time not available, use modification time
        timestamp=$(stat -c %Y "$dirname")
    else
        timestamp="$birthtime"
    fi
    
    # Format timestamp as YYYYMMDD-HHMMSS
    formatted_ts=$(date -d "@$timestamp" "+%Y%m%d-%H%M%S")
    
    # New directory name with timestamp prefix
    newname="${formatted_ts}_${dirname}"
    
    if [ -e "$newname" ]; then
        echo "Warning: '$newname' already exists, skipping '$dirname'"
        ((skipped++))
        continue
    fi
    
    echo "Renaming: $dirname -> $newname"
    mv "$dirname" "$newname"
    ((renamed++))
done

echo ""
echo "Done! Renamed: $renamed, Skipped: $skipped"

