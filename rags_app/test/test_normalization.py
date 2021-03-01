import pytest

from rags_src.rags_normalizer import RagsNormalizer
from rags_src.rags_core import DISEASE, CHEMICAL_SUBSTANCE, ROOT_ENTITY

@pytest.fixture()
def normalizer():
    return RagsNormalizer()


def test_node_normalization(normalizer):

    node_ids = ['MONDO:0011122',
                'CHEBI:27732',
                'FAKECURIE:1']

    normalized_nodes = normalizer.get_normalized_nodes(node_ids)

    test_node = normalized_nodes['MONDO:0011122']
    assert test_node.name == 'obesity disorder'
    assert 'DOID:9970' in test_node.synonyms
    assert 'MESH:D009765' in test_node.synonyms
    assert ROOT_ENTITY in test_node.all_types
    assert DISEASE in test_node.all_types

    test_node_2 = normalized_nodes['CHEBI:27732']
    assert test_node_2.name == 'CAFFEINE'
    assert test_node_2.id == 'PUBCHEM.COMPOUND:2519'
    assert CHEMICAL_SUBSTANCE in test_node_2.all_types

    assert normalized_nodes['FAKECURIE:1'] is None


def test_edge_normalization(normalizer):

    predicates = ['RO:0002610',
                  'RO:0000052',
                  'SEMMEDDB:CAUSES']

    normalized_predicates = normalizer.get_normalized_edges(predicates)

    assert normalized_predicates['RO:0002610'] == 'biolink:correlated_with'
    assert normalized_predicates['RO:0000052'] == 'biolink:related_to'
    assert normalized_predicates['SEMMEDDB:CAUSES'] == 'biolink:causes'





