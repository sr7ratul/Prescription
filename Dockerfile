# Use official Python base image
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Install system dependencies required by WeasyPrint
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    libffi-dev \
    fonts-liberation \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your project
COPY . .

# Expose port
EXPOSE 8080

# Start the app
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080"]
