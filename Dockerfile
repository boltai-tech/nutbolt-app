FROM condaforge/mambaforge:latest

WORKDIR /app

RUN conda create -y -n cadquery-env -c conda-forge cadquery=2.4.0 python=3.11 \
    && conda clean -afy

SHELL ["conda", "run", "-n", "cadquery-env", "/bin/bash", "-c"]

COPY requirements.txt .
RUN pip install --no-cache-dir fastapi uvicorn pydantic requests python-dotenv

COPY . .

EXPOSE 8000

CMD ["conda", "run", "--no-capture-output", "-n", "cadquery-env", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
