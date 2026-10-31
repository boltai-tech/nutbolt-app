FROM condaforge/miniforge3:latest

WORKDIR /app

RUN mamba create -y -n cadquery-env -c conda-forge cadquery=2.4.0 python=3.11     && mamba clean -afy

ENV PATH=/opt/conda/envs/cadquery-env/bin:$PATH     PYTHONUNBUFFERED=1     PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py kernel.py cad_builder.py catalog_templates.py ./

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
