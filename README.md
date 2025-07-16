# HR Finance Chatbot 🤖

A comprehensive AI-powered chatbot system for HR and Finance operations, featuring advanced data engineering, multi-agent AI orchestration, and real-time processing capabilities.

## 🚀 Features

### Data Engineering
- **Scalable Data Pipeline**: High-performance data processing using Polars
- **ETL Orchestration**: Apache Airflow for workflow management
- **Data Quality**: Great Expectations for validation and quality checks
- **Real-time Streaming**: Apache Kafka for real-time data processing
- **Change Data Capture**: Debezium for CDC implementation

### AI & ML Capabilities
- **Local AI Models**: Microsoft Phi-3 and Phi-2 integration
- **Semantic Kernel**: Advanced reasoning and multi-agent orchestration
- **RAG Pipeline**: Retrieval-Augmented Generation for context-aware responses
- **Vector Database**: ChromaDB for semantic search and document retrieval
- **Document Processing**: Intelligent document analysis and extraction

### Infrastructure
- **Containerized**: Docker and Docker Compose for easy deployment
- **API-First**: FastAPI with comprehensive REST endpoints
- **Monitoring**: Prometheus and Grafana for observability
- **Load Balancing**: Nginx reverse proxy
- **Database**: PostgreSQL with Redis caching

## 📋 Prerequisites

- Python 3.11+
- Docker and Docker Compose
- NVIDIA GPU (optional, for faster inference)
- At least 16GB RAM recommended

## 🛠️ Installation

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/hr-finance-chatbot.git
cd hr-finance-chatbot
```

### 2. Set up Environment
```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano .env
```

### 3. Install Dependencies
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 4. Set up Pre-commit Hooks
```bash
pre-commit install
```

## 🚀 Quick Start

### Using Docker Compose (Recommended)
```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f hr-finance-chatbot
```

### Manual Setup
```bash
# Start database
docker-compose up -d postgres redis

# Run migrations
python scripts/migrate.py

# Start the application
python main.py --mode api
```

## 📊 API Usage

### Start a Query
```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the average salary in the Engineering department?",
    "user_id": "user123",
    "department": "HR"
  }'
```

### Upload Document
```bash
curl -X POST "http://localhost:8000/document/upload" \
  -F "file=@policy.pdf" \
  -F "document_type=hr"
```

### Health Check
```bash
curl http://localhost:8000/health
```

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   User Interface │    │   API Gateway   │    │   AI Agents     │
│   (Frontend)     │◄──►│   (FastAPI)     │◄──►│   (Semantic     │
│                 │    │                 │    │   Kernel)       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                 │
                                 ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Data Pipeline │    │   Vector DB     │    │   ML Models     │
│   (Polars +     │◄──►│   (ChromaDB)    │◄──►│   (Phi-3/Phi-2)│
│   Airflow)      │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                        │
         ▼                        ▼
┌─────────────────┐    ┌─────────────────┐
│   Kafka Stream  │    │   PostgreSQL    │
│   (Real-time)   │    │   (Primary DB)  │
└─────────────────┘    └─────────────────┘
```

## 🔧 Configuration

### Environment Variables
Key configuration options in `.env`:

```bash
# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/hrfinance

# AI Models
PHI3_MODEL_PATH=microsoft/Phi-3-mini-4k-instruct
PHI2_MODEL_PATH=microsoft/phi-2

# Processing
BATCH_SIZE=1000
MAX_WORKERS=4
```

### Model Configuration
The system supports multiple AI models:
- **Phi-3**: Primary model for complex reasoning
- **Phi-2**: Lightweight model for simple queries
- **Sentence Transformers**: For embeddings and semantic search

## 📈 Monitoring

### Prometheus Metrics
Access metrics at: `http://localhost:9090`

Key metrics:
- Request latency
- Model inference time
- Data pipeline throughput
- Error rates

### Grafana Dashboards
Access dashboards at: `http://localhost:3000`
- Username: `admin`
- Password: `admin`

## 🧪 Testing

### Run All Tests
```bash
pytest
```

### Run Specific Test Categories
```bash
# Unit tests only
pytest -m unit

# Integration tests
pytest -m integration

# With coverage
pytest --cov=src --cov-report=html
```

### Load Testing
```bash
# Install locust
pip install locust

# Run load tests
locust -f tests/load/locustfile.py --host=http://localhost:8000
```

## 🚀 Deployment

### Production Deployment
```bash
# Build production image
docker build -t hr-finance-chatbot:prod .

# Deploy using docker-compose
docker-compose -f docker-compose.prod.yml up -d
```

### Kubernetes Deployment
```bash
# Apply Kubernetes manifests
kubectl apply -f k8s/
```

### CI/CD Pipeline
The project includes GitHub Actions workflows for:
- Code quality checks
- Testing
- Docker image building
- Automated deployment

## 📚 Documentation

- [API Documentation](docs/API.md)
- [Deployment Guide](docs/DEPLOYMENT.md)
- [Contributing Guidelines](docs/CONTRIBUTING.md)
- [Architecture Details](docs/ARCHITECTURE.md)

## 🛡️ Security

- JWT authentication for API access
- Rate limiting on all endpoints
- Input validation and sanitization
- Secure model serving
- Environment variable protection

## 🔍 Troubleshooting

### Common Issues

1. **Model Loading Issues**
   ```bash
   # Check model cache
   huggingface-cli download microsoft/Phi-3-mini-4k-instruct
   ```

2. **Database Connection**
   ```bash
   # Test connection
   docker-compose exec postgres psql -U postgres -d hrfinance
   ```

3. **Kafka Issues**
   ```bash
   # Check Kafka status
   docker-compose exec kafka kafka-topics --list --bootstrap-server localhost:9092
   ```

### Logs
```bash
# Application logs
docker-compose logs -f hr-finance-chatbot

# All services
docker-compose logs -f
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Support

For support, please:
1. Check the [documentation](docs/)
2. Search existing [issues](https://github.com/yourusername/hr-finance-chatbot/issues)
3. Create a new issue if needed

## 🙏 Acknowledgments

- Microsoft for Phi-3 and Phi-2 models
- Semantic Kernel team
- ChromaDB contributors
- FastAPI and Polars communities

## 📈 Roadmap

- [ ] Multi-language support
- [ ] Advanced analytics dashboard
- [ ] Voice interaction capability
- [ ] Mobile app integration
- [ ] Advanced security features
- [ ] Multi-tenant support

---

**Made with ❤️ by Your Team**