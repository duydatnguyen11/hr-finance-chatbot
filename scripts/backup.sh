#!/bin/bash
# Enhanced backup script for HR Finance Chatbot

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_ROOT}/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# Create backup directory
mkdir -p "$BACKUP_DIR"
cd "$PROJECT_ROOT"

log_info "Starting backup process at $(date)"

# Check if Docker Compose is running
if ! docker-compose ps | grep -q "Up"; then
    log_warn "Docker Compose services don't appear to be running"
    log_warn "Some backup operations may fail"
fi

# Backup PostgreSQL database
backup_database() {
    log_info "Backing up PostgreSQL database..."
    
    local db_backup_file="${BACKUP_DIR}/database_${TIMESTAMP}.sql"
    local db_backup_compressed="${db_backup_file}.gz"
    
    if docker-compose exec -T postgres pg_dump -U postgres hrfinance > "$db_backup_file" 2>/dev/null; then
        gzip "$db_backup_file"
        log_info "Database backup completed: $(basename "$db_backup_compressed")"
        
        # Verify backup
        if gunzip -t "$db_backup_compressed" 2>/dev/null; then
            log_info "Database backup verified successfully"
        else
            log_error "Database backup verification failed"
            return 1
        fi
    else
        log_error "Database backup failed"
        return 1
    fi
}

# Backup Redis data
backup_redis() {
    log_info "Backing up Redis data..."
    
    local redis_backup_file="${BACKUP_DIR}/redis_${TIMESTAMP}.rdb"
    
    # Create Redis snapshot
    if docker-compose exec -T redis redis-cli BGSAVE >/dev/null 2>&1; then
        sleep 2  # Wait for background save to complete
        
        # Copy Redis dump file
        if docker cp "$(docker-compose ps -q redis):/data/dump.rdb" "$redis_backup_file" 2>/dev/null; then
            log_info "Redis backup completed: $(basename "$redis_backup_file")"
        else
            log_warn "Redis backup copy failed, but BGSAVE was successful"
        fi
    else
        log_error "Redis backup failed"
        return 1
    fi
}

# Backup application data
backup_app_data() {
    log_info "Backing up application data..."
    
    local data_backup_file="${BACKUP_DIR}/app_data_${TIMESTAMP}.tar.gz"
    
    # Create tarball of data directory
    if tar -czf "$data_backup_file" -C "$PROJECT_ROOT" data/ --exclude="data/chroma_db/*.lock" 2>/dev/null; then
        log_info "Application data backup completed: $(basename "$data_backup_file")"
    else
        log_error "Application data backup failed"
        return 1
    fi
}

# Backup configuration files
backup_config() {
    log_info "Backing up configuration files..."
    
    local config_backup_file="${BACKUP_DIR}/config_${TIMESTAMP}.tar.gz"
    
    # Create tarball of configuration files
    if tar -czf "$config_backup_file" \
        .env \
        docker-compose.yml \
        docker-compose.prod.yml \
        nginx.conf \
        monitoring/ \
        k8s/ \
        --exclude="*.log" \
        --exclude="*.tmp" 2>/dev/null; then
        log_info "Configuration backup completed: $(basename "$config_backup_file")"
    else
        log_error "Configuration backup failed"
        return 1
    fi
}

# Backup vector database
backup_vector_db() {
    log_info "Backing up vector database..."
    
    local vector_backup_file="${BACKUP_DIR}/vector_db_${TIMESTAMP}.tar.gz"
    
    if [ -d "data/chroma_db" ]; then
        # Stop the application temporarily to ensure consistent backup
        local was_running=false
        if docker-compose ps hr-finance-chatbot | grep -q "Up"; then
            was_running=true
            log_debug "Stopping application for vector DB backup..."
            docker-compose stop hr-finance-chatbot >/dev/null 2>&1
        fi
        
        # Create backup
        if tar -czf "$vector_backup_file" -C "$PROJECT_ROOT" data/chroma_db/ 2>/dev/null; then
            log_info "Vector database backup completed: $(basename "$vector_backup_file")"
        else
            log_error "Vector database backup failed"
        fi
        
        # Restart application if it was running
        if [ "$was_running" = true ]; then
            log_debug "Restarting application..."
            docker-compose start hr-finance-chatbot >/dev/null 2>&1
        fi
    else
        log_warn "Vector database directory not found, skipping backup"
    fi
}

# Upload to cloud storage (optional)
upload_to_cloud() {
    log_info "Uploading backups to cloud storage..."
    
    if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$S3_BUCKET_NAME" ]; then
        log_debug "Uploading to AWS S3..."
        
        for backup_file in "${BACKUP_DIR}"/*_${TIMESTAMP}.*; do
            if [ -f "$backup_file" ]; then
                local filename=$(basename "$backup_file")
                if aws s3 cp "$backup_file" "s3://${S3_BUCKET_NAME}/backups/$(date +%Y/%m/%d)/$filename" 2>/dev/null; then
                    log_info "Uploaded to S3: $filename"
                else
                    log_error "Failed to upload to S3: $filename"
                fi
            fi
        done
    elif [ -n "$AZURE_STORAGE_CONNECTION_STRING" ] && [ -n "$AZURE_CONTAINER_NAME" ]; then
        log_debug "Uploading to Azure Blob Storage..."
        
        for backup_file in "${BACKUP_DIR}"/*_${TIMESTAMP}.*; do
            if [ -f "$backup_file" ]; then
                local filename=$(basename "$backup_file")
                if az storage blob upload \
                    --connection-string "$AZURE_STORAGE_CONNECTION_STRING" \
                    --container-name "$AZURE_CONTAINER_NAME" \
                    --name "backups/$(date +%Y/%m/%d)/$filename" \
                    --file "$backup_file" >/dev/null 2>&1; then
                    log_info "Uploaded to Azure: $filename"
                else
                    log_error "Failed to upload to Azure: $filename"
                fi
            fi
        done
    elif [ -n "$GCP_PROJECT_ID" ] && [ -n "$GCS_BUCKET_NAME" ]; then
        log_debug "Uploading to Google Cloud Storage..."
        
        for backup_file in "${BACKUP_DIR}"/*_${TIMESTAMP}.*; do
            if [ -f "$backup_file" ]; then
                local filename=$(basename "$backup_file")
                if gsutil cp "$backup_file" "gs://${GCS_BUCKET_NAME}/backups/$(date +%Y/%m/%d)/$filename" 2>/dev/null; then
                    log_info "Uploaded to GCS: $filename"
                else
                    log_error "Failed to upload to GCS: $filename"
                fi
            fi
        done
    else
        log_debug "No cloud storage configuration found, skipping upload"
    fi
}

# Cleanup old backups
cleanup_old_backups() {
    log_info "Cleaning up old backups (older than $RETENTION_DAYS days)..."
    
    local deleted_count=0
    
    # Find and delete old backup files
    while IFS= read -r -d '' file; do
        rm -f "$file"
        ((deleted_count++))
    done < <(find "$BACKUP_DIR" -name "*_[0-9]*.*" -mtime +$RETENTION_DAYS -print0 2>/dev/null)
    
    if [ $deleted_count -gt 0 ]; then
        log_info "Deleted $deleted_count old backup files"
    else
        log_debug "No old backup files to delete"
    fi
}

# Generate backup manifest
generate_manifest() {
    log_info "Generating backup manifest..."
    
    local manifest_file="${BACKUP_DIR}/manifest_${TIMESTAMP}.json"
    
    cat > "$manifest_file" << EOF
{
  "backup_timestamp": "$TIMESTAMP",
  "backup_date": "$(date -Iseconds)",
  "backup_type": "full",
  "files": [
EOF

    local first=true
    for backup_file in "${BACKUP_DIR}"/*_${TIMESTAMP}.*; do
        if [ -f "$backup_file" ] && [[ ! "$backup_file" == *"manifest"* ]]; then
            if [ "$first" = false ]; then
                echo "," >> "$manifest_file"
            fi
            
            local filename=$(basename "$backup_file")
            local filesize=$(stat -f%z "$backup_file" 2>/dev/null || stat -c%s "$backup_file" 2>/dev/null || echo "0")
            local checksum=$(sha256sum "$backup_file" | cut -d' ' -f1)
            
            cat >> "$manifest_file" << EOF
    {
      "filename": "$filename",
      "size": $filesize,
      "checksum": "$checksum"
    }EOF
            first=false
        fi
    done

    cat >> "$manifest_file" << EOF

  ],
  "environment": {
    "hostname": "$(hostname)",
    "user": "$(whoami)",
    "pwd": "$(pwd)"
  }
}
EOF

    log_info "Backup manifest created: $(basename "$manifest_file")"
}

# Send notification
send_notification() {
    local status="$1"
    local message="$2"
    
    if [ -n "$SLACK_WEBHOOK_URL" ]; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"🔄 Backup $status: $message\"}" \
            "$SLACK_WEBHOOK_URL" >/dev/null 2>&1
    fi
    
    if [ -n "$DISCORD_WEBHOOK_URL" ]; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"content\":\"🔄 Backup $status: $message\"}" \
            "$DISCORD_WEBHOOK_URL" >/dev/null 2>&1
    fi
}

# Main backup process
main() {
    local start_time=$(date +%s)
    local failed_operations=()
    
    log_info "HR Finance Chatbot Backup Script"
    log_info "Backup directory: $BACKUP_DIR"
    log_info "Timestamp: $TIMESTAMP"
    
    # Perform backups
    backup_database || failed_operations+=("database")
    backup_redis || failed_operations+=("redis")
    backup_app_data || failed_operations+=("app_data")
    backup_config || failed_operations+=("config")
    backup_vector_db || failed_operations+=("vector_db")
    
    # Generate manifest
    generate_manifest
    
    # Upload to cloud if configured
    upload_to_cloud
    
    # Cleanup old backups
    cleanup_old_backups
    
    # Calculate backup size and duration
    local total_size=0
    for backup_file in "${BACKUP_DIR}"/*_${TIMESTAMP}.*; do
        if [ -f "$backup_file" ]; then
            local filesize=$(stat -f%z "$backup_file" 2>/dev/null || stat -c%s "$backup_file" 2>/dev/null || echo "0")
            total_size=$((total_size + filesize))
        fi
    done
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local total_size_mb=$((total_size / 1024 / 1024))
    
    # Summary
    log_info "Backup process completed in ${duration}s"
    log_info "Total backup size: ${total_size_mb}MB"
    
    if [ ${#failed_operations[@]} -eq 0 ]; then
        log_info "All backup operations completed successfully! ✅"
        send_notification "Success" "All operations completed successfully (${total_size_mb}MB in ${duration}s)"
        exit 0
    else
        log_error "Some backup operations failed: ${failed_operations[*]}"
        send_notification "Partial Failure" "Failed operations: ${failed_operations[*]}"
        exit 1
    fi
}

# Command line options
case "${1:-}" in
    --help|-h)
        echo "HR Finance Chatbot Backup Script"
        echo ""
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --database     Backup database only"
        echo "  --redis        Backup Redis only"
        echo "  --data         Backup application data only"
        echo "  --config       Backup configuration only"
        echo "  --vector       Backup vector database only"
        echo "  --cleanup      Cleanup old backups only"
        echo ""
        echo "Environment Variables:"
        echo "  BACKUP_RETENTION_DAYS  Number of days to keep backups (default: 30)"
        echo "  S3_BUCKET_NAME         AWS S3 bucket for cloud backup"
        echo "  AZURE_CONTAINER_NAME   Azure container for cloud backup"
        echo "  GCS_BUCKET_NAME        Google Cloud Storage bucket"
        echo "  SLACK_WEBHOOK_URL      Slack webhook for notifications"
        echo "  DISCORD_WEBHOOK_URL    Discord webhook for notifications"
        exit 0
        ;;
    --database)
        backup_database
        ;;
    --redis)
        backup_redis
        ;;
    --data)
        backup_app_data
        ;;
    --config)
        backup_config
        ;;
    --vector)
        backup_vector_db
        ;;
    --cleanup)
        cleanup_old_backups
        ;;
    *)
        main
        ;;
esac