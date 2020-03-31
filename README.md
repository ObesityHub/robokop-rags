# Robokop Association Graphs

Robokop Association Graphs or RAGS is a tool for uploading results from association studies into a graph database for comparison and analysis. 

## Installation

### Prerequisites
[Install Docker](https://www.docker.com/get-started) if not installed on your computer. 

Make a ``<workspace>`` directory. 

```
$ mkdir <workspace>
$ cd <workspace> 
```

Inside the ``<workspace>`` directory, clone the repository.
```
$ git clone https://github.com/ObesityHub/robokop-rags.git
```

### Environment settings

Set up these required environment variables.

Create a text file at `<workspace>/rags.env`, parallel to the repository, and copy the following settings there. 

Change them as needed for your set up or use these defaults. 

In either case, you'll need to supply your own values for the secret variables at the end.


```
#################### RAGS Environmental Variables ####################

# Docker settings
COMPOSE_PROJECT_NAME=rags

# Graph DB - Neo4j
NEO4J_HOST=rags_graph
NEO4J_HTTP_PORT=7474
NEO4J_HTTPS_PORT=7473
NEO4J_BOLT_PORT=7687
NEO4J_HEAP_MEMORY=7G
NEO4J_HEAP_MEMORY_INIT=4G
NEO4J_CACHE_MEMORY=4G
NEO4J_READONLY=False

# Cache - Redis
RAGS_CACHE_HOST=rags_cache
RAGS_CACHE_PORT=6380
RAGS_CACHE_DB=0

# RAGS Application
RAGS_APP_HOST=rags_builder
RAGS_APP_PORT=80

# Service Endpoints
NODE_NORMALIZATION_ENDPOINT=https://nodenormalization-sri.renci.org/get_normalized_nodes

########################################################
####################### Secrets ########################
NEO4J_PASSWORD=*******
RAGS_CACHE_PASSWORD=*******
```

You can modify the following values to best fit your hardware. [Read more](https://neo4j.com/developer/guide-performance-tuning/).

```
NEO4J_HEAP_MEMORY
NEO4J_HEAP_MEMORY_INIT
NEO4J_CACHE_MEMORY
```


Run the following to make sure that your terminal is set up with the environment variables before running docker commands.

```
$ cd <workspace>/robokop-rags
$ source ./set_rags_env.sh
```

### Starting the Application Server
Start the docker containers:

```
$ cd <workspace>/robokop-rags
$ docker-compose up
```

## Using the Application

Put your association study files in this directory:
```
$ <workspace>/robokop-rags/rags_data/
```
You can move the sample files over if you'd like:
```
$ cd <workspace>
$ cp ./robokop-rags/rags_app/test/sample_data/* ./rags_data/
```
Use the web application interface at:
```
http://localhost
```
Then view the Neo4j graph directly at:
```
http://localhost:7474/browser/
```

### Testing and troubleshooting

You can run pytest tests inside of the application docker container. 

Enter the container:
```
$ docker exec -it rags_app bash
```
Run the tests:
```
$ cd test
$ pytest
```



