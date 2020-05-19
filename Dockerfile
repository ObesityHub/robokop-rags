FROM tiangolo/uvicorn-gunicorn-fastapi:python3.7

ARG UID=1000
ARG GID=1000
RUN groupadd -o -g $GID rags_user
RUN useradd -m -u $UID -g $GID -s /bin/bash rags_user

ENV USER=rags_user
ENV RAGS_HOME=/rags

COPY ./rags_app /rags/rags_app
RUN pip install -r /rags/rags_app/requirements.txt --src /usr/local/src

WORKDIR /rags/
RUN git clone https://github.com/ObesityHub/robokop-genetics.git
RUN pip install /rags/robokop-genetics

ENV PYTHONPATH="$PYTHONPATH:/rags/rags_app"
WORKDIR /rags/rags_app


