import pytest

from rags_src.rags_graph_db import RagsGraphDB
from rags_src.rags_core import RAGsNode, RAGsEdge
from rags_src.rags_graph_writer import BufferedWriter
from rags_src.rags_core import SEQUENCE_VARIANT, ROOT_ENTITY, TESTING_NODE


@pytest.fixture()
def graph_db():
    return RagsGraphDB()


def test_node_writer(graph_db):

    graph_db.custom_write_query(f'match (a:`{TESTING_NODE}`) detach delete a')

    with BufferedWriter(graph_db) as writer:
        for i in range(1, 51):
            test_node = RAGsNode(f'TESTING:{i}', TESTING_NODE, name=f'Fake Name {i}')
            test_node.synonyms = [f'ALT_FAKE_CURIE:{i}', f'DIFFERENT_FAKE_CURIE:{i}']
            test_node.all_types = frozenset([TESTING_NODE])
            writer.write_node(test_node)

    query = f'match (a:`{TESTING_NODE}`) return a.id as id, a.name as name, a.equivalent_identifiers as synonyms'
    print(query)
    results = graph_db.custom_read_query(query)
    assert len(results) >= 50

    verified = 0
    for result in results:
        for i in range(1, 51):
            if result['id'] == f'TESTING:{i}':
                if result['name'] == f'Fake Name {i}':
                    if result['synonyms'] == [f'ALT_FAKE_CURIE:{i}', f'DIFFERENT_FAKE_CURIE:{i}']:
                        verified += 1
                        continue
    assert verified == 50

    verified = 0
    for result in results:
        for i in range(1, 51):
            if result[0] == f'TESTING:{i}':
                if result[1] == f'Fake Name {i}':
                    if result[2] == [f'ALT_FAKE_CURIE:{i}', f'DIFFERENT_FAKE_CURIE:{i}']:
                        verified += 1
                        continue
    assert verified == 50

    graph_db.custom_write_query(f'match (a:`{TESTING_NODE}`) detach delete a')
    results = graph_db.custom_read_query(f'match (a:`{TESTING_NODE}`) return a.id as id')
    assert len(results) == 0


def test_edge_writer(graph_db):

    graph_db.custom_write_query(f'match (a:`{TESTING_NODE}`) detach delete a')

    with BufferedWriter(graph_db) as writer:
        for i in range(1, 11):
            test_node = RAGsNode(f'TESTING:{i}', TESTING_NODE, name=f'Fake Name {i}')
            test_node.synonyms = [f'ALT_FAKE_CURIE:{i}', f'DIFFERENT_FAKE_CURIE:{i}']
            test_node.all_types = frozenset([TESTING_NODE])
            writer.write_node(test_node)

        for i in range(1, 11):
            for k in range(1, 11):
                test_edge = RAGsEdge(id=None,
                                     subject_id=f'TESTING:{i}',
                                     object_id=f'TESTING:{k}',
                                     original_object_id=f'TESTING:{i}_{k}_input',
                                     predicate='TESTING:test_predicate',
                                     relation='TESTING:test_relation',
                                     provided_by='RAGS_Testing',
                                     namespace='fake_namespace',
                                     project_id=99999,
                                     project_name='Fake Project Name',
                                     properties={'testing_property': 1})
                writer.write_edge(test_edge)

    results = graph_db.custom_read_query(f'match (a:`{TESTING_NODE}`)-[r]-(b:`{TESTING_NODE}`) return count(distinct r) as edge_count')
    assert results[0]['edge_count'] == 100

    results = graph_db.custom_read_query(f'match (a:`{TESTING_NODE}`)-[r]-(b:`{TESTING_NODE}`) return r.testing_property', 1)
    assert results[0][0] == 1

    graph_db.custom_write_query(f'match (a:`{TESTING_NODE}`) detach delete a')





