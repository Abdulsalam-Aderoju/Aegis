# specify python image
FROM python:3.13-slim


# set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# copy project
COPY . .

# EXPOSE PORT
EXPOSE 8000

# RUN SERVER
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]