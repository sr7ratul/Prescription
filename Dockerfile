# Use an official Python image
FROM python:3.11-slim

# Install system dependencies required by WeasyPrint
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy all files
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 8080

# Run using gunicorn
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080"]
