FROM python:3.13-slim

WORKDIR /app

# System dependencies for building Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency wheel first (for layer caching)
COPY Dependency/ Dependency/
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create data and logs directories
RUN mkdir -p data logs

# Expose Streamlit port
EXPOSE 8501

# Default: run the dashboard
CMD ["streamlit", "run", "dashboard/app_ui.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--server.headless", "true"]
