#!/bin/bash

function printHelp(){
    echo "
        A simple script to take off a running neo4j container and reload a dump file into it
        then bring it back up. File argument is optional. graph.latest.db.dump will be loaded if 
        -f is not provided.
        Arguments:
            -f    file          file name to reload eg '-f graph.latest.db.dump' .
            -c    compose-file  Path to the docker-compose file to start Neo4j in backup mode.
            -h    help          display this message.

    "
}

# Default to latest if args are not provided
backup_file='graph.db.latest.dump'
compose_file_location='docker-compose-backup.yml'
while getopts :hf:c: opt; do
    case $opt in 
        h) 
        printHelp
        exit
        ;;
        f) 
        backup_file=$OPTARG
        ;;
        c)
        compose_file_location=$OPTARG
        ;;
        \?) 
        echo "Invalid option -$OPTARG" 
        printHelp
        exit 1
        ;;
    esac
done
backup_file='//data/'$backup_file
echo loading "$backup_file"
if [ $(docker ps -f name=rags_graph -q) ]; then
    echo "killing graph container..."
    docker kill $(docker ps -f name=rags_graph -q)
    echo "graph container down..."
fi

echo "creating new container for loading..."
docker-compose -f $compose_file_location up -d

#docker exec $(docker ps -f name=rags_graph -q) ls -lh $backup_file

echo "loading graph ..."
docker exec $(docker ps -f name=rags_graph -q) bash bin/neo4j-admin load --from $backup_file --force true

echo "killing graph loading container..."
docker kill $(docker ps -f name=rags_graph -q)

echo "loading graph complete..."
