
from rags_src.graph_components import KNode
from rags_src.rags_graph_builder import RAG
from rags_src.rags_file_tools import GWASFileReader
from rags_src.rags_core import SignificantHitsContainer
from rags_src.rags_graph_db import RagsGraphDB
from rags_src.rags_normalizer import RagsNormalizer
from typing import NamedTuple


class GWASValidationInfo(NamedTuple):
    success: bool
    message: str
    details: str = None


class RagsValidator(object):

    def __init__(self, graph_db: RagsGraphDB):
        self.graph_db = graph_db
        self.normalizer = RagsNormalizer()

    def validate_associations(self,
                              project_id: str,
                              gwas_build: RAG,
                              variant_bucket: SignificantHitsContainer,
                              verbose: bool = False):

        expected_associations = 0
        p_value_too_high = 0
        missing_variants_count = 0
        missing_variants = []
        with GWASFileReader(gwas_build.gwas_file, use_tabix=gwas_build.gwas_file.has_tabix) as gwas_file_reader:
            for variant in variant_bucket.iterate_all_variants():
                association = gwas_file_reader.get_gwas_association_from_file(variant)
                if association:
                    if (gwas_build.max_p_value is None) or (association.p_value <= gwas_build.max_p_value):
                        expected_associations += 1
                    elif gwas_build.max_p_value:
                        p_value_too_high += 1
                else:
                    missing_variants_count += 1
                    if verbose:
                        missing_variants.append(variant)

        if not (expected_associations or p_value_too_high or missing_variants_count):
            return GWASValidationInfo(False, f'Failed. Missing or corrupt file!')

        gwas_node = KNode(gwas_build.was_node_curie,
                          name=gwas_build.was_node_label,
                          type=gwas_build.was_node_type)
        self.normalizer.normalize(gwas_node)
        real_was_node_curie = gwas_node.id

        details = f'The file was missing variants: {", ".join(str(var) for var in missing_variants)}' if verbose else None

        custom_query = f"match ({{id: '{real_was_node_curie}' }})-[:related_to {{project_id: '{project_id}', namespace: '{gwas_build.build_name}'}}]-(s) return count(distinct s)"
        var_list = self.graph_db.query_the_graph(custom_query)
        if var_list:
            hit_count = int(var_list[0][0])
            if hit_count == expected_associations:
                return GWASValidationInfo(True, f'Passed. {expected_associations} confirmed written to the graph.', details)
            else:
                missing_associations = expected_associations - hit_count
                return GWASValidationInfo(False, f'Failed. Missing {missing_associations} associations of {expected_associations}!', details)
        else:
            return GWASValidationInfo(False, f'Error querying the graph!')
