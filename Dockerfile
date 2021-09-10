FROM tiangolo/uvicorn-gunicorn-fastapi:python3.8

ENV JAVA_HOME=/opt/java/openjdk
COPY --from=eclipse-temurin:11 $JAVA_HOME $JAVA_HOME
ENV PATH="${JAVA_HOME}/bin:${PATH}"

ARG UID=1000
ARG GID=1000
RUN groupadd -o -g $GID rags_user
RUN useradd -m -u $UID -g $GID -s /bin/bash rags_user

ENV USER=rags_user
ENV RAGS_HOME=/rags

COPY ./rags_app /rags/rags_app
RUN pip install -r /rags/rags_app/requirements.txt --src /usr/local/src

ENV PYTHONPATH="$PYTHONPATH:/rags/rags_app"
WORKDIR /rags/rags_app


