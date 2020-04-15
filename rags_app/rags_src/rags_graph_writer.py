import rags_src.node_types as node_types
from rags_src.util import LoggingUtil, Text
from rags_src.rags_graph_db import RagsGraphDB

from collections import defaultdict
import logging
import os

logger = LoggingUtil.init_logging("rags.export", logging.INFO, format='medium',
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
        self.node_buffer_size = 100
        self.edge_buffer_size = 100
        self.maxWrittenNodes = 100000
        self.maxWrittenEdges = 100000
        self.graph_db = graph_db

    def __enter__(self):
        return self

    def write_node(self, node):
        if node.id in self.written_nodes:
            return
        if node.name is None or node.name == '':
            logger.warning(f"Writing Node {node.id}, it's missing a label")
        else:
            #logger.info(f"Writing Node {node.id}, label=({node.name})")
            pass

        #self.export_graph.add_type_labels(node)
        self.written_nodes.add(node.id)
        node_queue = self.node_queues[node.type]
        node_queue.append(node)
        if len(node_queue) == self.node_buffer_size:
            self.flush()

    def write_edge(self, edge):
        if edge in self.written_edges[edge.source_id][edge.target_id]:
            return
        else:
            self.written_edges[edge.source_id][edge.target_id].add(edge)

        label = Text.snakify(edge.standard_predicate.label)
        edge_queue = self.edge_queues[label]
        edge_queue.append(edge)
        if len(edge_queue) >= self.edge_buffer_size:
            self.flush()

    def flush(self):
        with self.graph_db.get_session() as session:
            for node_type in self.node_queues:
                session.write_transaction(export_node_chunk, self.node_queues[node_type], node_type)
                self.node_queues[node_type] = []

            for edge_label in self.edge_queues:
                session.write_transaction(export_edge_chunk, self.edge_queues[edge_label],
                                          edge_label)
                self.edge_queues[edge_label] = []

            # clear the memory on a threshold boundary to avoid using up all memory when
            # processing large data sets
            if len(self.written_nodes) > self.maxWrittenNodes:
                self.written_nodes.clear()

            if len(self.written_edges) > self.maxWrittenEdges:
                self.written_edges.clear()

    def __exit__(self, *args):
        self.flush()


def export_edge_chunk(tx, edge_list, edge_label):

    cypher = f"""UNWIND $batches as row
            MATCH (a:{node_types.ROOT_ENTITY} {{id: row.source_id}}),(b:{node_types.ROOT_ENTITY} {{id: row.target_id}})
            MERGE (a)-[r:{edge_label} {{id: apoc.util.md5([a.id, b.id, '{edge_label}', row.namespace, row.project_id]), predicate_id: row.standard_id}}]->(b)
            ON CREATE SET r.edge_source = [row.provided_by]
            ON CREATE SET r.relation_label = [row.original_predicate_label]
            ON CREATE SET r.source_database=[row.database]
            ON CREATE SET r.ctime=[row.ctime]
            ON CREATE SET r.publications=row.publications
            ON CREATE SET r.relation = [row.original_predicate_id]
            ON CREATE SET r += row.properties
            ON CREATE SET r.namespace=row.namespace
            ON CREATE SET r.project_id=row.project_id
            ON CREATE SET r.project_name=row.project_name
            FOREACH (_ IN CASE WHEN row.provided_by in r.edge_source THEN [] ELSE [1] END |
            SET r.edge_source = CASE WHEN EXISTS(r.edge_source) THEN r.edge_source + [row.provided_by] ELSE [row.provided_by] END
            SET r.ctime = CASE WHEN EXISTS (r.ctime) THEN r.ctime + [row.ctime] ELSE [row.ctime] END
            SET r.relation_label = CASE WHEN EXISTS(r.relation_label) THEN r.relation_label + [row.original_predicate_label] ELSE [row.original_predicate_label] END
            SET r.source_database = CASE WHEN EXISTS(r.source_database) THEN r.source_database + [row.database] ELSE [row.database] END
            SET r.predicate_id = row.standard_id
            SET r.relation = CASE WHEN EXISTS(r.relation) THEN r.relation + [row.original_predicate_id] ELSE [row.original_predicate_id] END
            SET r.publications = [pub in row.publications where not pub in r.publications ] + r.publications
            SET r += row.properties
            )"""

    batch = [{'source_id': edge.source_id,
              'target_id': edge.target_id,
              'provided_by': edge.provided_by,
              'database': edge.provided_by.split('.')[0],
              'ctime': edge.ctime,
              'namespace': edge.namespace,
              'project_id': edge.project_id if edge.project_id else None,
              'project_name': edge.project_name if edge.project_name else None,
              'standard_id': edge.standard_predicate.identifier,
              'original_predicate_id': edge.original_predicate.identifier,
              'original_predicate_label': edge.original_predicate.label,
              'publication_count': len(edge.publications),
              'publications': edge.publications[:1000],
              'properties': edge.properties if edge.properties is not None else {}
              }
             for edge in edge_list]

    tx.run(cypher, {'batches': batch})

    for edge in edge_list:
        if edge.standard_predicate.identifier == 'GAMMA:0':
            logger.warn(f"Unable to map predicate for edge {edge.original_predicate}  {edge}")


def export_node_chunk(tx, node_list, node_type):
    cypher = f"""UNWIND {{batches}} AS batch
                MERGE (a:{node_types.ROOT_ENTITY} {{id: batch.id}})
                ON CREATE SET a:{node_types.ROOT_ENTITY}
                ON CREATE SET a:{node_type}
                ON CREATE SET a += batch.properties"""
    logger.warning(f'using cypher: {cypher}')
    batch = []
    for n in node_list:
        n.properties['equivalent_identifiers'] = [s.identifier for s in n.synonyms]
        if n.name is not None:
            n.properties['name'] = n.name
            #logger.warning(f"Setting {n.id} name property to {n.name}")
        export_node = {'id': n.id, 'name': n.name, 'properties': n.properties}
        #logger.warning(f"Exporting {export_node}")
        batch.append(export_node)
    tx.run(cypher, {'batches': batch})