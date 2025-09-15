# Student Card Reader 🎓

A Python-based server component for reading and verifying student ID cards as part of a comprehensive roommate finder application. This service provides secure student identity verification by processing physical student ID cards and validating them against verified student email addresses.

## 🏗️ Architecture Overview

This card reader server is a microservice component of a larger roommate finder application built with:
- **Backend**: Spring Boot (Main application server)
- **Frontend**: Vue.js (User interface)
- **Identity Service**: Python (This repository - Student card verification)

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Vue.js        │    │   Spring Boot    │    │   Python        │
│   Frontend      │◄──►│   Backend        │◄──►│   Card Reader   │
│                 │    │                  │    │   Server        │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🎯 Purpose

The Student Card Reader serves as a crucial identity verification component that:
- **Enhances Security**: Ensures only verified students can access the roommate finder platform
- **Builds Trust**: Provides confidence that users are legitimate students
- **Prevents Fraud**: Reduces fake profiles and unauthorized access
- **Streamlines Onboarding**: Automates the student verification process

## ✨ Features

- 📷 **Physical Card Scanning**: Reads student ID cards using camera/scanner
- 🔍 **OCR Processing**: Extracts student information from card images
- ✉️ **Email Verification**: Validates student email addresses
- 🔐 **Secure API**: RESTful endpoints for integration with main application
- 📊 **Verification Status**: Returns detailed verification results
- 🏫 **Multi-Institution Support**: Configurable for different universities
- 📝 **Audit Logging**: Tracks verification attempts and results

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- pip package manager
- Camera/Scanner hardware (for card reading)
- Access to student email verification system

### Installation

1. **Clone the repository**
   ```bash
   git clone git@github.com:staybuddies/id_card_reader.git
   cd id_card_reader
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Run the server**
   ```bash
   python app.py
   ```

The server will start on `http://localhost:5000` by default.

## 🔧 Configuration

Create a `.env` file in the root directory:

```env
# Server Configuration
PORT=5000
DEBUG=True
HOST=0.0.0.0

# Database Configuration
DATABASE_URL=your_database_connection_string

# Email Service Configuration
SMTP_SERVER=your_smtp_server
SMTP_PORT=587
EMAIL_USERNAME=your_email_username
EMAIL_PASSWORD=your_email_password

# OCR Service Configuration
OCR_API_KEY=your_ocr_api_key
OCR_ENDPOINT=your_ocr_service_endpoint

# Security Configuration
JWT_SECRET_KEY=your_jwt_secret_key
API_KEY=your_api_key_for_spring_boot_integration

# University Configuration
SUPPORTED_INSTITUTIONS=university1.edu,university2.edu
```

## 📡 API Endpoints

### POST `/api/verify-card`
Verify a student ID card and email combination.

**Request:**
```json
{
  "card_image": "base64_encoded_image",
  "student_email": "student@university.edu",
  "institution": "university.edu"
}
```

**Response:**
```json
{
  "success": true,
  "verification_id": "uuid-string",
  "student_info": {
    "student_id": "12345678",
    "name": "John Doe",
    "institution": "University Name",
    "email_verified": true
  },
  "confidence_score": 0.95,
  "timestamp": "2024-03-15T10:30:00Z"
}
```

### GET `/api/verification-status/{verification_id}`
Check the status of a verification request.

### POST `/api/resend-verification`
Resend verification email to student.

## 🔄 Integration with Main Application

### Spring Boot Integration

Add this service to your Spring Boot application by calling the verification endpoint:

```java
@Service
public class StudentVerificationService {
    
    @Value("${card-reader.base-url}")
    private String cardReaderBaseUrl;
    
    public VerificationResult verifyStudent(String cardImage, String email) {
        // HTTP call to Python service
        return restTemplate.postForObject(
            cardReaderBaseUrl + "/api/verify-card",
            request,
            VerificationResult.class
        );
    }
}
```

### Vue.js Frontend Integration

```javascript
// Student verification component
export default {
  methods: {
    async verifyStudentCard(cardImage, email) {
      try {
        const response = await this.$http.post('/api/students/verify', {
          card_image: cardImage,
          student_email: email
        });
        return response.data;
      } catch (error) {
        console.error('Verification failed:', error);
        throw error;
      }
    }
  }
}
```

## 🛠️ Development

### Running in Development Mode

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run with hot reload
python app.py --debug

# Run tests
python -m pytest tests/

# Code formatting
black .
flake8 .
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_verification.py
```

## 📦 Deployment

### Docker Deployment

```bash
# Build image
docker build -t student-card-reader .

# Run container
docker run -p 5000:5000 --env-file .env student-card-reader
```

### Production Environment

1. Set `DEBUG=False` in production
2. Use a production WSGI server like Gunicorn
3. Configure proper logging
4. Set up SSL/TLS certificates
5. Implement rate limiting
6. Configure monitoring and health checks

## 🔒 Security Considerations

- **API Authentication**: All endpoints require valid API keys
- **Data Encryption**: Sensitive data encrypted in transit and at rest
- **Input Validation**: All inputs sanitized and validated
- **Rate Limiting**: Protection against abuse and DoS attacks
- **Audit Logging**: All verification attempts logged for security analysis
- **GDPR Compliance**: Student data handling complies with privacy regulations

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📋 Requirements

See `requirements.txt` for a full list of dependencies.

Key dependencies:
- Flask/FastAPI (Web framework)
- OpenCV (Image processing)
- Tesseract (OCR)
- SQLAlchemy (Database ORM)
- Requests (HTTP client)
- Pillow (Image manipulation)

## 🆘 Troubleshooting

### Common Issues

**OCR not working properly**
- Ensure Tesseract is properly installed
- Check image quality and resolution
- Verify OCR configuration settings

**Email verification failing**
- Check SMTP configuration
- Verify email server credentials
- Ensure proper firewall/security group settings

**Database connection issues**
- Verify database URL format
- Check database server accessibility
- Ensure proper credentials

## 📞 Support

For issues related to the main roommate finder application, please refer to the main repository.

For card reader specific issues:
- Create an issue in this repository
- Contact: zwenyanwin001@gmail.com

---

**Part of the StayBuddies Roommate Finder Platform** 🏠

*Making student housing connections safer and more trustworthy through verified identity.*
