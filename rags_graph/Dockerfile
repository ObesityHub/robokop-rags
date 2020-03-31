FROM neo4j:3.5.4

ENV APOC_URI https://github.com/neo4j-contrib/neo4j-apoc-procedures/releases/download/3.5.0.2/apoc-3.5.0.2-all.jar

RUN mkdir /plugins

RUN wget $APOC_URI \
    && mv apoc-3.5.0.2-all.jar /plugins

EXPOSE 7474 7473 7687

CMD ["neo4j"]