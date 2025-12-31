#!/bin/bash
# Script to validate MinIO (S3) setup
# Tests bucket creation, upload, download, and cleanup

set -e

echo "=========================================="
echo "  MinIO (S3) Validation Script"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
TEST_FILE="test-upload-$(date +%s).txt"
TEST_CONTENT="MinIO validation test at $(date)"
TEST_BUCKET="raw-events"

# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $2"
    else
        echo -e "${RED}✗${NC} $2"
        exit 1
    fi
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# 1. Check if MinIO is accessible
echo "1. Checking MinIO connectivity..."
if docker compose -f infra/docker-compose.yml exec minio mc alias list | grep -q "local"; then
    print_status 0 "MinIO is accessible"
else
    # Try to set alias
    docker compose -f infra/docker-compose.yml exec minio sh -c 'mc alias set local http://localhost:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD}' &>/dev/null && \
        print_status 0 "MinIO is accessible (alias configured)" || \
        print_status 1 "MinIO is NOT accessible"
fi
echo ""

# 2. List existing buckets
echo "2. Listing existing buckets..."
docker compose -f infra/docker-compose.yml exec minio mc ls local
echo ""

# 3. Verify required buckets exist
echo "3. Verifying required buckets..."
REQUIRED_BUCKETS=(
    "raw-events"
    "pipeline-artifacts"
)

for bucket in "${REQUIRED_BUCKETS[@]}"; do
    if docker compose -f infra/docker-compose.yml exec minio mc stat local/${bucket} &>/dev/null; then
        print_status 0 "Bucket '${bucket}' exists"
    else
        echo -e "${RED}✗${NC} Bucket '${bucket}' is MISSING"
    fi
done
echo ""

# 4. Create test file
echo "4. Creating test file..."
echo "${TEST_CONTENT}" > /tmp/${TEST_FILE}
print_status 0 "Test file created: /tmp/${TEST_FILE}"
echo ""

# 5. Upload test file
echo "5. Uploading test file to MinIO..."
docker compose -f infra/docker-compose.yml exec -T minio sh -c "echo '${TEST_CONTENT}' | mc pipe local/${TEST_BUCKET}/test/${TEST_FILE}" &>/dev/null && \
    print_status 0 "File uploaded successfully" || \
    print_status 1 "Failed to upload file"
echo ""

# 6. List files in test directory
echo "6. Listing files in test directory..."
docker compose -f infra/docker-compose.yml exec minio mc ls local/${TEST_BUCKET}/test/
echo ""

# 7. Download test file
echo "7. Downloading test file from MinIO..."
DOWNLOADED_CONTENT=$(docker compose -f infra/docker-compose.yml exec minio mc cat local/${TEST_BUCKET}/test/${TEST_FILE} 2>/dev/null)
if [ "$DOWNLOADED_CONTENT" == "$TEST_CONTENT" ]; then
    print_status 0 "File downloaded and content matches"
    print_info "Content: ${DOWNLOADED_CONTENT}"
else
    print_status 1 "File content does not match"
fi
echo ""

# 8. Get file stats
echo "8. File statistics..."
docker compose -f infra/docker-compose.yml exec minio mc stat local/${TEST_BUCKET}/test/${TEST_FILE}
echo ""

# 9. Cleanup
read -p "Delete test file from MinIO? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker compose -f infra/docker-compose.yml exec minio mc rm local/${TEST_BUCKET}/test/${TEST_FILE} &>/dev/null && \
        print_status 0 "Test file deleted from MinIO" || \
        echo -e "${YELLOW}⚠${NC} Could not delete test file"
fi

# Cleanup local file
rm -f /tmp/${TEST_FILE}

echo ""
echo "=========================================="
echo -e "${GREEN}✓ MinIO validation completed successfully!${NC}"
echo "=========================================="
