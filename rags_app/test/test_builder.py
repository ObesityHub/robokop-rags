import pytest

from rags_src.rags_graph_db import RagsGraphDB
from rags_src.graph_components import KNode, KEdge, LabeledID
import rags_src.node_types as node_types
from rags_src.rags_graph_writer import BufferedWriter


@pytest.fixture()
def graph_db():
    return RagsGraphDB()


def test_node_writer(graph_db):

    graph_db.query_the_graph('match (a) where a.testing = 1 detach delete a')
    results = graph_db.query_the_graph('match (a) where a.testing = 1 return a.id')
    assert len(results) == 0

    with BufferedWriter(graph_db) as writer:
        for i in range(1, 51):
            test_node = KNode(f'FAKECURIE:{i}', node_types.SEQUENCE_VARIANT, name=f'Fake Name {i}')
            test_node.properties['testing'] = 1
            test_node.synonyms = [f'ALT_FAKE_CURIE:{i}', f'DIFFERENT_FAKE_CURIE:{i}']
            writer.write_node(test_node)

        writer.flush()

    results = graph_db.query_the_graph('match (a) where a.testing = 1 return a.id, a.name, a.equivalent_identifiers')
    assert len(results) >= 50
    verified = 0
    for result in results:
        for i in range(1, 51):
            if result[0] == f'FAKECURIE:{i}':
                if result[1] == f'Fake Name {i}':
                    if result[2] == [f'ALT_FAKE_CURIE:{i}', f'DIFFERENT_FAKE_CURIE:{i}']:
                        verified += 1
                        continue
    assert verified == 50

    graph_db.query_the_graph('match (a) where a.testing = 1 detach delete a')
    results = graph_db.query_the_graph('match (a) where a.testing = 1 return a.id')
    assert len(results) == 0




