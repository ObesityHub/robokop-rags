import pytest
from collections import defaultdict
from rags_src.rags_core import RAGsNode, RAGsEdge, SEQUENCE_VARIANT
from rags_src.rags_variant_annotation import SequenceVariantAnnotator

from robokop_genetics.genetics_normalization import GeneticsNormalizer


def test_snpeff_annotation():

    genetics_normalizer = GeneticsNormalizer(use_cache=False)

    #variant_ids = ['CAID:CA36853879']

    variant_ids = [
        # deletions
        'CAID:CA36853879',
        'CAID:CA36203597',
        # insertions
        'CAID:CA916079866', # on X chromosome
        # missense snps
        'CAID:CA321211',
        'CAID:CA123309']

    sequence_variant_normalizations = genetics_normalizer.normalize_variants(variant_ids)

    variant_nodes = []
    for variant_id, variant_normalizations in sequence_variant_normalizations.items():
        variant_normalization = variant_normalizations[0]
        variant_node = RAGsNode(variant_normalization['id'],
                                type=SEQUENCE_VARIANT,
                                name="",
                                synonyms=variant_normalization['equivalent_identifiers'])
        variant_nodes.append(variant_node)

    variant_annotator = SequenceVariantAnnotator()
    annotation_results = variant_annotator.get_variant_annotations(variant_nodes)

    edge_dict = defaultdict(lambda: defaultdict(list))
    for edge in annotation_results['edges']:
        edge_dict[edge.subject_id][edge.predicate].append(edge)

    for subject_id, subject_dict in edge_dict.items():
        for predicate_id, edges in subject_dict.items():
            print(f'{subject_id} - {predicate_id} - {len(edges)}')

    assert len(edge_dict['CAID:CA36853879']['SNPEFF:upstream_gene_variant']) == 19
    assert len(edge_dict['CAID:CA36853879']['GAMMA:0000102']) == 2

    assert len(edge_dict['CAID:CA321211']['SNPEFF:missense_variant']) > 0
    assert len(edge_dict['CAID:CA123309']['SNPEFF:missense_variant']) > 0
