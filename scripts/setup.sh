#!/bin/bash
# scripts/setup.sh - Project Setup Script

set -e  # Exit on any error

echo "🚀 HR Finance Chatbot Setup Script"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check Python version
    if ! command -v python3.11 &> /dev/null; then
        if ! command -v python3 &> /dev/null; then
            print_error "Python 3.11+ is required but not installed."
            exit 1
        else
            PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
            if [[ "$(printf '%s\n' "3.11" "$PYTHON_VERSION" | sort -V | head -n1)" != "3.11" ]]; then
                print_error "Python 3.11+ is required. Found version $PYTHON_VERSION"
                exit 1
            fi
        fi
    fi
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is required but not installed."
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is required but not installed."
        exit 1
    fi
    
    # Check Git
    if ! command -v git &> /dev/null; then
        print_error "Git is required but not installed."
        exit 1
    fi
    
    print_status "All prerequisites satisfied ✅"
}

# Create project structure
create_directories() {
    print_status "Creating project directories..."
    
    directories=(
        "data/raw"
        "data/processed"
        "data/models"
        "data/chroma_db"
        "logs"
        "monitoring/grafana/dashboards"
        "monitoring/grafana/datasources"
        "scripts"
        "docs"
        "tests/fixtures"
        "dags"
        "src/config"
        "src/data"
        "src/ai"
        "src/api"
        "src/utils"
    )
    
    for dir in "${directories[@]}"; do
        mkdir -p "$dir"
        echo "Created: $dir"
    done
    
    # Create .gitkeep files for empty directories
    touch data/raw/.gitkeep
    touch data/processed/.gitkeep
    touch logs/.gitkeep
    
    print_status "Directory structure created ✅"
}

# Setup virtual environment
setup_venv() {
    print_status "Setting up Python virtual environment..."
    
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        print_status "Virtual environment created"
    else
        print_warning "Virtual environment already exists"
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Upgrade pip
    python -m pip install --upgrade pip
    
    print_status "Virtual environment ready ✅"
}

# Install dependencies
install_dependencies() {
    print_status "Installing Python dependencies..."
    
    if [ ! -f "requirements.txt" ]; then
        print_error "requirements.txt not found"
        exit 1
    fi
    
    # Install requirements
    pip install -r requirements.txt
    
    print_status "Dependencies installed ✅"
}

# Setup environment file
setup_environment() {
    print_status "Setting up environment configuration..."
    
    if [ ! -f ".env" ]; then
        cat > .env << 'EOF'
# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/hrfinance
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password
POSTGRES_DB=hrfinance

# Redis
REDIS_URL=redis://localhost:6379

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# AI Models
PHI3_MODEL_PATH=microsoft/Phi-3-mini-4k-instruct
PHI2_MODEL_PATH=microsoft/phi-2
EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2

# API
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Security
SECRET_KEY=your-secret-key-here-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=30

# Monitoring
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
EOF
        print_status "Environment file created (.env)"
        print_warning "Please update the SECRET_KEY in .env file!"
    else
        print_warning ".env file already exists"
    fi
}

# Setup pre-commit hooks
setup_precommit() {
    print_status "Setting up pre-commit hooks..."
    
    if command -v pre-commit &> /dev/null; then
        pre-commit install
        print_status "Pre-commit hooks installed ✅"
    else
        print_warning "pre-commit not found, skipping hook installation"
    fi
}

# Download AI models
download_models() {
    print_status "Downloading AI models..."
    
    python -c "
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from sentence_transformers import SentenceTransformer

print('Downloading Phi-3 model...')
try:
    tokenizer = AutoTokenizer.from_pretrained('microsoft/Phi-3-mini-4k-instruct')
    model = AutoModelForCausalLM.from_pretrained('microsoft/Phi-3-mini-4k-instruct')
    print('Phi-3 model downloaded successfully')
except Exception as e:
    print(f'Error downloading Phi-3: {e}')

print('Downloading embedding model...')
try:
    model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
    print('Embedding model downloaded successfully')
except Exception as e:
    print(f'Error downloading embedding model: {e}')
"
    
    print_status "Model download completed ✅"
}

# Initialize database
init_database() {
    print_status "Initializing database..."
    
    # Start only database services
    docker-compose up -d postgres redis
    
    # Wait for database to be ready
    print_status "Waiting for database to be ready..."
    sleep 10
    
    # Run database initialization
    docker-compose exec -T postgres psql -U postgres -c "CREATE DATABASE IF NOT EXISTS hrfinance;"
    docker-compose exec -T postgres psql -U postgres -c "CREATE DATABASE IF NOT EXISTS airflow;"
    
    print_status "Database initialized ✅"
}

# Setup monitoring
setup_monitoring() {
    print_status "Setting up monitoring configuration..."
    
    # Prometheus configuration
    mkdir -p monitoring
    cat > monitoring/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'hr-finance-chatbot'
    static_configs:
      - targets: ['hr-finance-chatbot:8000']
    metrics_path: '/metrics'
    
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
EOF
    
    print_status "Monitoring configuration created ✅"
}

# Main setup function
main() {
    print_status "Starting HR Finance Chatbot setup..."
    
    check_prerequisites
    create_directories
    setup_venv
    install_dependencies
    setup_environment
    setup_precommit
    download_models
    setup_monitoring
    
    print_status "Setup completed successfully! 🎉"
    print_status ""
    print_status "Next steps:"
    print_status "1. Update the .env file with your configuration"
    print_status "2. Run: docker-compose up -d"
    print_status "3. Access the API at: http://localhost:8000"
    print_status "4. Access Grafana at: http://localhost:3000"
    print_status ""
    print_warning "Don't forget to change the SECRET_KEY in .env for production!"
}

# Run main function if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi

# scripts/deploy.sh - Deployment Script

#!/bin/bash
# scripts/deploy.sh - Production Deployment Script

set -e

echo "🚀 HR Finance Chatbot Deployment Script"
echo "======================================="

# Configuration
ENVIRONMENT=${1:-production}
VERSION=${2:-latest}
REGISTRY=${DOCKER_REGISTRY:-""}

print_status() {
    echo -e "\033[0;32m[INFO]\033[0m $1"
}

print_error() {
    echo -e "\033[0;31m[ERROR]\033[0m $1"
}

# Pre-deployment checks
pre_deployment_checks() {
    print_status "Running pre-deployment checks..."
    
    # Check if .env exists
    if [ ! -f ".env" ]; then
        print_error ".env file not found"
        exit 1
    fi
    
    # Check Docker
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running"
        exit 1
    fi
    
    # Run tests
    print_status "Running tests..."
    python -m pytest tests/ -v
    
    print_status "Pre-deployment checks passed ✅"
}

# Build Docker images
build_images() {
    print_status "Building Docker images..."
    
    # Build main application image
    docker build -t hr-finance-chatbot:${VERSION} .
    
    if [ ! -z "$REGISTRY" ]; then
        docker tag hr-finance-chatbot:${VERSION} ${REGISTRY}/hr-finance-chatbot:${VERSION}
        docker push ${REGISTRY}/hr-finance-chatbot:${VERSION}
    fi
    
    print_status "Docker images built successfully ✅"
}

# Deploy application
deploy_application() {
    print_status "Deploying application..."
    
    if [ "$ENVIRONMENT" == "production" ]; then
        docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
    else
        docker-compose up -d
    fi
    
    print_status "Application deployed ✅"
}

# Health check
health_check() {
    print_status "Performing health check..."
    
    # Wait for application to start
    sleep 30
    
    # Check application health
    max_attempts=30
    attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f http://localhost:8000/health > /dev/null 2>&1; then
            print_status "Health check passed ✅"
            return 0
        fi
        
        print_status "Attempt $attempt/$max_attempts - waiting for application to be ready..."
        sleep 10
        ((attempt++))
    done
    
    print_error "Health check failed after $max_attempts attempts"
    return 1
}

# Backup database
backup_database() {
    if [ "$ENVIRONMENT" == "production" ]; then
        print_status "Creating database backup..."
        
        timestamp=$(date +%Y%m%d_%H%M%S)
        docker-compose exec -T postgres pg_dump -U postgres hrfinance > "backups/hrfinance_${timestamp}.sql"
        
        print_status "Database backup created ✅"
    fi
}

# Main deployment function
main() {
    print_status "Starting deployment for environment: $ENVIRONMENT"
    
    pre_deployment_checks
    backup_database
    build_images
    deploy_application
    health_check
    
    print_status "Deployment completed successfully! 🎉"
    print_status "Application is available at: http://localhost:8000"
}

# Run main function
main "$@"

# scripts/backup.sh - Backup Script

#!/bin/bash
# scripts/backup.sh - Backup Script

set -e

BACKUP_DIR="backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

print_status() {
    echo -e "\033[0;32m[INFO]\033[0m $1"
}

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup database
print_status "Backing up PostgreSQL database..."
docker-compose exec -T postgres pg_dump -U postgres hrfinance > "${BACKUP_DIR}/hrfinance_${TIMESTAMP}.sql"

# Backup Redis data
print_status "Backing up Redis data..."
docker-compose exec -T redis redis-cli BGSAVE
docker cp $(docker-compose ps -q redis):/data/dump.rdb "${BACKUP_DIR}/redis_${TIMESTAMP}.rdb"

# Backup application data
print_status "Backing up application data..."
tar -czf "${BACKUP_DIR}/data_${TIMESTAMP}.tar.gz" data/

# Backup configuration
print_status "Backing up configuration..."
tar -czf "${BACKUP_DIR}/config_${TIMESTAMP}.tar.gz" .env docker-compose.yml monitoring/

print_status "Backup completed successfully! ✅"
print_status "Backup files created in: $BACKUP_DIR"
ls -la $BACKUP_DIR/*${TIMESTAMP}*