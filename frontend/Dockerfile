FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install packages first so this layer is cached between code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app.py and the .streamlit/config.toml folder into /app.
COPY . .

EXPOSE 8501

# headless: don't try to open a browser or ask for an email inside the container.
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]