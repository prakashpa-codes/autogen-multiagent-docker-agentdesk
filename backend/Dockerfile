# Start from an official slim Python image (Debian Linux + Python 3.13).
FROM python:3.13-slim

# Show print() output immediately in the container logs.
ENV PYTHONUNBUFFERED=1

# All following commands run inside /app in the image.
WORKDIR /app

# Install packages first so this slow layer is cached between code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend code into /app/backend so "from backend.agents import ..." still works.
COPY . ./backend

# Document the port the app listens on.
EXPOSE 8000

# Start the API. 0.0.0.0 makes it reachable from outside the container.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
