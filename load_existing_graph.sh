#!/usr/bin/env bash
# make sure this directory exists, otherwise we might fail on the first time through
mkdir -p "$RAGS_HOME"/neo4j_data/databases/graph.db

# if we have a base graph URL, grab it from the URL
if [ "$RAGS_BASE_GRAPH_URL" != "None" ]; then
    echo "loading graph at $RAGS_BASE_GRAPH_URL"
    curl -o "$RAGS_HOME/neo4j_data/graph.db.latest.dump" "$RAGS_BASE_GRAPH_URL"
fi

# check to make sure we have a dump file
if test -f "$RAGS_HOME/neo4j_data/graph.db.latest.dump"; then
    ./rags_graph/scripts/reload.sh -c ./rags_graph/scripts/docker-compose-backup.yml
else
    echo "Error: No dump file found at ../neo4j_data/graph.db.latest.dump"
    echo "You must specify the dump file URL with the environment variable RAGS_BASE_GRAPH_URL or provide one."
fi