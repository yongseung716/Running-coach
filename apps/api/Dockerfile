FROM python:3.12-slim
WORKDIR /app
COPY apps/api/pyproject.toml ./
COPY apps/api/coach ./coach
RUN pip install --no-cache-dir .
ENV MODE=production
EXPOSE 8000
CMD ["uvicorn", "coach.main:app", "--host", "0.0.0.0", "--port", "8000"]
