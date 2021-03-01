
from rags_src.rags_core import RAGsNode
from rags_src.rags_graph_db import RagsGraphDB
from rags_src.rags_project_db_models import RAGsStudy
from typing import NamedTuple


class GWASValidationInfo(NamedTuple):
    success: bool
    message: str
    details: str = None


class RagsValidator(object):

    def __init__(self, graph_db: RagsGraphDB):
        self.graph_db = graph_db

    def validate_associations(self,
                              project_id: str,
                              study: RAGsStudy,
                              num_expected_associations: int):

        associated_node = RAGsNode(study.normalized_trait_id,
                                   name=study.normalized_trait_label,
                                   type=study.trait_type)

        custom_query = f"match ({{id: '{associated_node.id}' }})-[:correlated_with {{project_id: '{project_id}', namespace: '{study.study_name}'}}]-(s) return count(distinct s)"
        var_list = self.graph_db.custom_read_query(custom_query)
        if var_list:
            association_count = int(var_list[0][0])
            if association_count == num_expected_associations:
                return {"success": True, "success_message": f"{num_total_hits} associations found in graph.", "num_associations": association_count}
            else:
                missing_associations = num_expected_associations - association_count
                return {"success": False, "error_message": f'Failed. Missing {missing_associations} associations of {num_total_hits}!'}
        else:
            return {"success": False, "error_message": f'Failed. No associations found.'}
