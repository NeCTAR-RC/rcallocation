FROM python:3.14-slim-trixie

EXPOSE 5000

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Install pip requirements
COPY requirements.txt .

RUN apt update && apt install -y gcc

RUN python -m pip install -c https://releases.openstack.org/constraints/upper/2026.1 -r requirements.txt
RUN python -m pip install -c https://releases.openstack.org/constraints/upper/2026.1 gunicorn

WORKDIR /app
COPY dist/* /app

RUN python -m pip install -c https://releases.openstack.org/constraints/upper/2026.1 *.tar.gz && rm *.tar.gz

# Creates a non-root user and adds permission to access the /app folder
RUN useradd -u 42420 appuser && chown -R appuser /app
USER appuser

# --no-control-socket: gunicorn 25 defaults the control socket to
# $HOME/.gunicorn/, which fails on a read-only root filesystem.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--access-logfile=-", "--worker-tmp-dir", "/dev/shm", "--no-control-socket", "--workers", "2", "rcallocation.wsgi:application"]
