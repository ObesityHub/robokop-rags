#!/bin/bash

compose_file="scripts/docker-compose-backup.yml"
graph_compose_file="docker-compose.yml"

function printHelp(){
    echo "
        This script will take a back up of the neo4j database.
        Usage:
            ./backup.sh
        Arguments:
            -h   help                      display this message.
    "
}


while getopts :hc:f: opt; do
    case $opt in 
        h) 
        printHelp
        exit
        ;;
        \?) 
        echo "Invalid option -$OPTARG" 
        printHelp
        exit 1
        ;;
    esac
done

docker kill $(docker ps -f name=rags_graph -q)

docker-compose -f "./docker-compose-backup.yml" up -d

# ------------- back up process start 


# when killing containers New neo4j complains 'Active Logical log detected', 
# and needs a clean shutdown :/

docker exec $(docker ps -f name=rags_graph -q) bash -c "bin/neo4j start; bin/neo4j stop"


#
current_date=$(date +"%Y-%m-%d")
docker exec $(docker ps -f name=rags_graph -q) bash bin/neo4j-admin dump --to "data/graph_${current_date}.db.dump"


# kill back-upper container
docker kill $(docker ps -f name=rags_graph -q)
echo "Back up complete - (graph_${current_date}.db.dump)."
# ------------------ back up complete

