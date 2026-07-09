FROM python:3.11-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data
COPY preprocess.py .

# Build safemeal_pure.db from the raw label JSON at image build time so the
# container starts instantly and needs no network access at runtime.
RUN python preprocess.py

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
