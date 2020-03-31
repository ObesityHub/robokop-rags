
from rags_src.rags_cache import Cache
from rags_src.graph_components import KNode, LabeledID
from rags_src.util import LoggingUtil, Text
from rags_src.services.clingen import ClinGenService
import rags_src.node_types as node_types

import logging
import requests
import os

logger = LoggingUtil.init_logging("rags.synonymizer", logging.INFO, format='medium', logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')


class Synonymizer(object):

    def __init__(self, cache: Cache):
        self.node_normalization_url = os.environ["NODE_NORMALIZATION_ENDPOINT"]
        self.cache = cache
        self.clingen = ClinGenService()

    def synonymize(self, node: KNode):

        key = f"normalization({Text.upper_curie(node.id)})"
        # Check the cache. If it's not in there, call the API
        try:
            normalization = self.cache.get(key)
            #normalization = None
        except Exception as e:
            logger.warning(e)
            normalization = None
        if normalization:
            logger.debug(f"cache hit: {key}")
        else:
            if node.type == node_types.SEQUENCE_VARIANT:
                normalization = self.get_sequence_variant_normalization(node)
            else:
                normalization = self.get_other_nodes_normalization(node)

            self.cache.set(key, normalization)

        if normalization:
            node.id = normalization[0]
            node.name = normalization[1]
            node.synonyms = normalization[2]

    def get_other_nodes_normalization(self, node: KNode):
        requested_curie = node.id
        payload = {'curie': requested_curie}
        r = requests.get(self.node_normalization_url, params=payload)
        if r.status_code != 200:
            logger.warning(
                f'Node Normalization returned a non-200 response({r.status_code}) calling ({r.url})')
        else:
            response_json = r.json()
            if requested_curie in response_json:
                normalized_result = response_json[requested_curie]
                best_id = normalized_result["id"]
                node.id = best_id["identifier"]
                if "label" in best_id:
                    node.name = best_id["label"]
                normalized_synonyms = set()
                for syn in normalized_result["equivalent_identifiers"]:
                    if "label" in syn:
                        normalized_synonyms.add(LabeledID(identifier=syn["identifier"], label=syn["label"]))
                    else:
                        normalized_synonyms.add(LabeledID(identifier=syn["identifier"]))

                node.synonyms = normalized_synonyms

        return [node.id, node.name, node.synonyms]

    def get_sequence_variant_normalization(self, node:KNode):
        syns = self.get_sequence_variant_synonyms(node)
        node.synonyms = syns
        caids = node.get_synonyms_by_prefix('CAID')
        if caids:
            caid = next(iter(caids))
            node.id = caid
            node.name = Text.un_curie(caid)

        return [node.id, node.name, node.synonyms]

    def get_sequence_variant_synonyms(self, node: KNode):
        synonyms = set()
        caids = node.get_synonyms_by_prefix('CAID')
        if caids:
            synonyms.update(self.clingen.get_synonyms_by_caid(Text.un_curie(caids.pop())))
        else:
            synonyms.update(self.clingen.get_synonyms_by_other_ids(node))
        return synonyms
