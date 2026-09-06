FROM python:3.10-slim

# Install system dependencies: FFmpeg and multi-lingual fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    fonts-noto-core \
    fonts-noto-cjk \
    fonts-noto-extra \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and assets
COPY . .

# Expose port for Hugging Face Spaces / Cloud hosting
EXPOSE 7860
ENV PORT=7860
ENV APP_PORT=7860
ENV PYTHONUNBUFFERED=1

# Launch server
CMD ["python", "server.py"]
