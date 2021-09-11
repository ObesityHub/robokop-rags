from rags_src.rags_core import ROOT_ENTITY, RAGsEdge, RAGsNode, ORIGINAL_KNOWLEDGE_SOURCE
from rags_src.util import LoggingUtil
from rags_src.rags_graph_db import RagsGraphDB

from collections import defaultdict
import logging
import os

logger = LoggingUtil.init_logging("rags.rags_graph_writer", logging.INFO,
                                  format='medium',
                                  logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')


class BufferedWriter(object):
    """Buffered writer accepts individual nodes and edges to write to neo4j.
    It doesn't write the node/edge if it has already been written in its lifetime (it maintains a record)
    It then accumulates nodes/edges by label/type until a buffersize has been reached, at which point it does
    an intelligent update/write to the batch of nodes and edges.

    The correct way to use this is
    with BufferedWriter(rosetta) as writer:
        writer.write_node(node)
        ...

    Doing this as a context manager will make sure that the different queues all get flushed out.
    """
    def __init__(self, graph_db: RagsGraphDB):
        self.written_nodes = set()
        self.written_edges = defaultdict(lambda: defaultdict(set))
        self.node_queues = defaultdict(list)
        self.edge_queues = defaultdict(list)
        self.node_buffer_size = 10000
        self.edge_buffer_size = 10000
        self.graph_db = graph_db

    def __enter__(self):
        return self

    def write_node(self, node: RAGsNode):
        if not node or node.id in self.written_nodes:
            return

        self.written_nodes.add(node.id)
        node_queue = self.node_queues[node.all_types]
        node_queue.append(node)
        if len(node_queue) == self.node_buffer_size:
            self.flush()

    def write_edge(self, edge: RAGsEdge):
        #if edge in self.written_edges[edge.subject_id][edge.object_id]:
        #    return
        #else:
        #    self.written_edges[edge.subject_id][edge.object_id].add(edge)

        edge_queue = self.edge_queues[edge.predicate]
        edge_queue.append(edge)
        if len(edge_queue) >= self.edge_buffer_size:
            self.flush()

    def flush(self):
        with self.graph_db.get_session() as session:
            for node_type_set in self.node_queues:
                session.write_transaction(write_batch_of_nodes,
                                          self.node_queues[node_type_set],
                                          node_type_set)
                self.node_queues[node_type_set] = []

            for predicate in self.edge_queues:
                session.write_transaction(write_batch_of_edges,
                                          self.edge_queues[predicate],
                                          predicate)
                self.edge_queues[predicate] = []

    def __exit__(self, *args):
        self.flush()


def write_batch_of_edges(tx, batch_of_edges: list, predicate):

    cypher = f"""UNWIND $edge_batch as edge
            MATCH (a:`{ROOT_ENTITY}` {{id: edge.subject_id}}),(b:`{ROOT_ENTITY}` {{id: edge.object_id}})            
            CREATE (a)-[r:`{predicate}` {{
            project_id: edge.project_id,
            project_name: edge.project_name,
            namespace: edge.namespace,
            input_id: edge.input_id,
            relation: edge.relation,
            `{ORIGINAL_KNOWLEDGE_SOURCE}`: edge.provided_by}}]->(b)
            SET r += edge.properties"""

    edges_as_dicts = [{'subject_id': edge.subject_id,
                       'object_id': edge.object_id,
                       'input_id': edge.original_object_id,
                       'relation': edge.relation,
                       'provided_by': edge.provided_by if edge.provided_by else None,
                       'namespace': edge.namespace if edge.namespace else None,
                       'project_id': edge.project_id if edge.project_id else None,
                       'project_name': edge.project_name if edge.project_name else None,
                       'properties': edge.properties if edge.properties else {}} for edge in batch_of_edges]

    tx.run(cypher, {'edge_batch': edges_as_dicts})


def write_batch_of_nodes(tx, batch_of_nodes, node_type_set):

    cypher = f"""UNWIND $batch AS node
                MERGE (a:`{ROOT_ENTITY}` {{id: node.id}}) """
    for node_type in node_type_set:
        cypher += f"ON CREATE SET a:`{node_type}` "
    cypher += "ON CREATE SET a += node.properties"

    node_dicts = []
    for n in batch_of_nodes:
        n.properties['equivalent_identifiers'] = list(n.synonyms)
        n.properties['category'] = list(node_type_set)
        n.properties['name'] = n.name
        export_node = {'id': n.id,  'properties': n.properties}
        node_dicts.append(export_node)

    tx.run(cypher, {'batch': node_dicts})
