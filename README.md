# Robokop Association Graphs

Robokop Association Graphs or RAGs is a tool for uploading results from association studies into a Knowledge Graph database for comparison and analysis. 

## Installation

### Prerequisites
[Install Docker](https://www.docker.com/get-started) if it is not installed already. 

Make a new directory for RAGs (referred to as ``<workspace>``). ``<workspace>`` can be any directory, for example: ~/rags_workspace/

```
$ mkdir <workspace>
$ cd <workspace> 
```

Inside the ``<workspace>`` directory, clone the repository.
```
$ git clone https://github.com/ObesityHub/robokop-rags.git
```

### Environment settings

Set the required environment variables.

Create the settings file: `<workspace>/rags.env`

Copy the following settings there. Change them as needed for your set up or use these defaults.

```
#################### RAGS Environmental Variables ####################

# Docker settings
COMPOSE_PROJECT_NAME=rags

# RAGS Application
RAGS_APP_PORT=80
RAGS_APP_DATA_DIR=../rags_data

# Use a graph db dump from the url
RAGS_BASE_GRAPH_URL=https://robokopkg.renci.org/normalize_graph+genetics.dump.db
# Or switch to this for a local or empty graph
# RAGS_BASE_GRAPH_URL=None

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

# Genetics Cache - Redis 
# Optional cache to store genetics normalization and other information.
# Using a cache will improve speed and performance if genetic variants are loaded multiple times.
# https://github.com/ObesityHub/robokop-genetics
# ROBO_GENETICS_CACHE_HOST=rags_cache
# ROBO_GENETICS_CACHE_PORT=6380
# ROBO_GENETICS_CACHE_DB=1
# ROBO_GENETICS_CACHE_PASSWORD=yourpassword

# Optional - Alternate Service Endpoints
# NODE_NORMALIZATION_ENDPOINT=https://nodenormalization.renci.org/alternate_endpoint
# EDGE_NORMALIZATION_ENDPOINT=https://edgenormalization.renci.org/alternate_endpoint
```

### Set up a Knowledge Graph
There are two options for pre-loading a knowledge graph:

##### Option A

Specify the URL of a knowledge graph in your environment settings. The graph will be downloaded and incorporated automatically. The default will load our latest Robokop Knowledge Graph.

```
RAGS_BASE_GRAPH_URL=http://robokopkg.renci.org/latest-graph.db
```

##### Option B

Alternatively, if you already have a knowledge graph from a Neo4j 4.2 admin dump, move your dump file and rename it so that it matches the path below. Create the neo4j_data directory if it doesn't exist.
```
<workspace>/neo4j_data/graph.db.latest.dump
```
When using your own knowledge graph, you must set the environment setting to None.
```
RAGS_BASE_GRAPH_URL=None
```


## Starting the Application
Run the following commands to prepare your environment. The script will utilize the environment variables you set earlier.

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

#### Memory Issues and Crashes

If the rags_graph neo4j container fails to start, or crashes, you may have issues with memory management.

You can modify these values in the rags.env file to best utilize your hardware. [Read more](https://neo4j.com/developer/guide-performance-tuning/).

```
NEO4J_HEAP_MEMORY
NEO4J_HEAP_MEMORY_INIT
NEO4J_CACHE_MEMORY
```

You may also have to configure the amount of memory available for Docker. 

Docker will need to be able to use at least the amount specified by NEO4J_HEAP_MEMORY plus NEO4J_CACHE_MEMORY.

If using Docker Desktop, this is easy to configure in preferences. See [here](https://docs.docker.com/docker-for-mac/#resources).


## Using the Application

First move your association study files into a directory accessible to RAGs.

By default, you can use the following directory. It will be created for you when you start the application.
```
$ <workspace>/rags_data/
```
Alternatively, you can specify any directory you'd like by changing this environment variable to your own path:
```
RAGS_APP_DATA_DIR=/example/path/on_your_machine
```
You can move some sample files over if you'd like to see examples:
```
$ cd <workspace>
$ cp ./robokop-rags/rags_app/test/sample_data/* ./rags_data/
```
OR if you used a different data directory
```
$ cp ./robokop-rags/rags_app/test/sample_data/* /example/path/on_your_machine/
```

Then use the web application interface at:
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
$ pytest
```
