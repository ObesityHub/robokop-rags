import pytest

from rags_src.rags_core import RAGsNode, SEQUENCE_VARIANT
from rags_src.rags_variant_annotation import SequenceVariantAnnotator

from robokop_genetics.genetics_normalization import GeneticsNormalizer


def test_snpeff_annotation():

    genetics_normalizer = GeneticsNormalizer(use_cache=False)

    variant_ids = ['CAID:CA36853879',
                   'HGVS:NC_000014.9:g.64442127G>A']

    sequence_variant_normalizations = genetics_normalizer.normalize_variants(variant_ids)

    variant_nodes = []
    for variant_id, variant_normalizations in sequence_variant_normalizations.items():
        variant_normalization = variant_normalizations[0]
        variant_node = RAGsNode(variant_normalization['id'],
                                type=SEQUENCE_VARIANT,
                                name="",
                                synonyms=variant_normalization['equivalent_identifiers'])
        variant_nodes.append(variant_node)
        #print(variant_normalization['id'])
        #print(variant_normalization['equivalent_identifiers'])

    variant_annotator = SequenceVariantAnnotator()
    annotation_results = variant_annotator.get_variant_annotations(variant_nodes)
    #print(annotation_results)

    #for edge in annotation_results['edges']:
    #    print(edge)

    assert len(annotation_results['edges']) > 10



