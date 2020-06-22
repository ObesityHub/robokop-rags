#!/usr/bin/env bash
# make sure this directory exists, otherwise we might fail on the first time through
mkdir -p "$RAGS_HOME"/neo4j_data/databases/graph.db

# if the base graph URL setting is on and no graph is found, grab it from the URL
if [ "$RAGS_BASE_GRAPH_URL" != "None" ]; then
    if ! test -f "$RAGS_HOME/neo4j_data/graph.db.latest.dump"; then
        echo "downloading graph from $RAGS_BASE_GRAPH_URL"
        curl -o "$RAGS_HOME/neo4j_data/graph.db.latest.dump" "$RAGS_BASE_GRAPH_URL"
    fi
fi

# call a script to load the dump file into the neo4j graph
# this will create the neo4j container if it doesn't exist yet
if test -f "$RAGS_HOME/neo4j_data/graph.db.latest.dump"; then
    echo "Graph back up found, loading now..."
    ./rags_graph/scripts/reload.sh -c ./rags_graph/scripts/docker-compose-backup.yml
else
    echo "Error: No dump file found at ../neo4j_data/graph.db.latest.dump"
    echo "You must specify the dump file URL with the environment variable RAGS_BASE_GRAPH_URL or provide one."
fi