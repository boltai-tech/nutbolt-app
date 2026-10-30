FROM condaforge/miniforge3:latest

WORKDIR /app

# CadQuery/OpenCASCADE come from conda-forge (pip wheels are heavy and slow to build)
RUN mamba create -y -n cadquery-env -c conda-forge cadquery=2.4.0 python=3.11 \
    && mamba clean -afy

# Put the env on PATH: no `conda run` wrapper => faster start, unbuffered logs, correct signals
ENV PATH=/opt/conda/envs/cadquery-env/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py kernel.py ./

# Render injects $PORT (default 10000); fall back to 8000 locally. One worker: 512MB RAM.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
