# Robokop Association Graphs

Robokop Association Graphs or RAGS is a tool for uploading results from association studies into a graph database for comparison and analysis. 

## Installation

### Prerequisites
[Install Docker](https://www.docker.com/get-started) if not installed on your computer. 

Make a ``<workspace>`` directory. ``<workspace>`` can be any directory, for example: ~/rags_workspace/

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

Create the text file: `<workspace>/rags.env`, parallel to the repository, and copy the following settings there. 

Change them as needed for your set up or use these defaults.

```
#################### RAGS Environmental Variables ####################

# Docker settings
COMPOSE_PROJECT_NAME=rags

# Graph DB - Neo4j
NEO4J_HOST=rags_graph
NEO4J_HTTP_PORT=7474
NEO4J_HTTPS_PORT=7473
NEO4J_BOLT_PORT=7687
NEO4J_HEAP_MEMORY=6G
NEO4J_HEAP_MEMORY_INIT=6G
NEO4J_CACHE_MEMORY=4G
NEO4J_READONLY=False
NEO4J_PASSWORD=yourpassword

#RAGS_BASE_GRAPH_URL=None
RAGS_BASE_GRAPH_URL=https://robokopkg.renci.org/normalize_graph+genetics.dump.db

# Cache - Redis
RAGS_CACHE_HOST=rags_cache
RAGS_CACHE_PORT=6380
RAGS_CACHE_DB=0
RAGS_CACHE_PASSWORD=yourpassword

# Genetics Cache - Redis
ROBO_GENETICS_CACHE_HOST=rags_cache
ROBO_GENETICS_CACHE_PORT=6380
ROBO_GENETICS_CACHE_DB=1
ROBO_GENETICS_CACHE_PASSWORD=yourpassword

# RAGS Application
RAGS_APP_HOST=rags_builder
RAGS_APP_PORT=80
RAGS_DATA_MOUNTED_VOLUME=../rags_data

# Service Endpoints
NODE_NORMALIZATION_ENDPOINT=https://nodenormalization-sri.renci.org/get_normalized_nodes

```

If you have memory issues or crashes, you can modify these values to best utilize your hardware. [Read more](https://neo4j.com/developer/guide-performance-tuning/).

```
NEO4J_HEAP_MEMORY
NEO4J_HEAP_MEMORY_INIT
NEO4J_CACHE_MEMORY
```

### Set up a Knowledge Graph
There are two options for pre-loading a knowledge graph:

##### Option A

Specify the URL of a knowledge graph in your environment settings. The graph will be downloaded and incorporated automatically. The default will load our latest Robokop Knowledge Graph.

```
RAGS_BASE_GRAPH_URL=http://robokopkg.renci.org/latest-graph.db
```

##### Option B

Alternatively, if you already have a knowledge graph from a Neo4j 3.5 admin dump, move your dump file and rename it so that it matches the path below. Create the neo4j_data directory if it doesn't exist.
```
<workspace>/neo4j_data/graph.db.latest.dump
```
When using your own knowledge graph, you must set the environment setting to None.
```
RAGS_BASE_GRAPH_URL=None
```


## Starting the Application
Run the following to make sure you're in the right place, and your terminal is set up with the environment variables.

```
$ cd <workspace>/robokop-rags
$ source ./set_rags_env.sh
```

If you set up a Knowledge Graph in previous steps, you still need to load it. This may take a few minutes or more depending on the size of the graph.

Run the following script to load the graph:
```
$ source ./load_existing_graph.sh
```

Finally, start the docker containers:

```
$ docker-compose up
```

## Using the Application

Put your association study files in this directory:
```
$ <workspace>/rags_data/
```
You can move some sample files over if you'd like to see examples:
```
$ cd <workspace>
$ cp ./robokop-rags/rags_app/test/sample_data/* ./rags_data/
```
Use the web application interface at:
```
http://localhost
```
To load your own association studies into the graph, create a project.
```
http://localhost/projects/
```
Clicking the gear icon next to your project switches to the edit project view.

Here you can enter the information needed to create RAGs (Association Graphs).

You can create a csv file with all of the information for your RAGs. (Need more info here). For example, to load the sample data you can click (+ Add Studies by File). Select the sample_rags.csv file.

You can also enter information for one study at a time. (+ Add an Association Study)

After you enter the RAGs information, click Search For Hits to scan the files for associations.

Finally, click Build Graph to load your association studies into the graph.

You can click Query Graph to view results using our preconfigured queries.

You can also view the Neo4j graph directly at:
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
