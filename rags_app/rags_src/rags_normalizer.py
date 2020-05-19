from rags_src.rags_cache import Cache
from rags_src.graph_components import KNode, LabeledID
from rags_src.util import LoggingUtil, Text
from rags_src import node_types
from robokop_genetics.genetics_normalization import GeneticsNormalizer

import logging
import requests
import os

logger = LoggingUtil.init_logging("rags.normalizer", logging.INFO, format='medium', logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')


class RagsNormalizer(object):

    def __init__(self, cache: Cache):
        self.node_normalization_url = os.environ["NODE_NORMALIZATION_ENDPOINT"]
        self.cache = cache
        self.genetics_normalizer = GeneticsNormalizer()

    def set_normalization(self, node_id: str, normalization: tuple, cache_pipe=None):
        key = f"normalization({node_id})"
        self.cache.set(key, normalization, cache_pipe)

    def get_normalization(self, node_id: str):
        key = f"normalization({node_id})"
        return self.cache.get(key)

    def normalize(self, node: KNode):
        # Check the cache. If it's not in there, go find it.
        try:
            normalization = self.get_normalization(node.id)
        except Exception as e:
            logger.warning(e)
            normalization = None
        if normalization is not None:
            #logger.info(f"cache hit: {key} {normalization}")
            pass
        else:
            if node.type == node_types.SEQUENCE_VARIANT:
                normalization = self.get_sequence_variant_normalization(node)
            else:
                normalization = self.get_other_nodes_normalization(node)

            self.set_normalization(node.id, normalization)

        if normalization and normalization != (None, None, None):
            normalized_id, normalized_name, synonyms = normalization
            node.id = normalized_id
            node.name = normalized_name
            node.synonyms = synonyms
        else:
            if not node.name:
                node.name = Text.un_curie(node.id)

    def get_other_nodes_normalization(self, requested_curie: str):
        payload = {'curie': requested_curie}
        r = requests.get(self.node_normalization_url, params=payload)
        if r.status_code != 200:
            logger.warning(
                f'Node Normalization returned a non-200 response({r.status_code}) calling ({r.url})')
            return None, None, None
        else:
            response_json = r.json()
            if requested_curie in response_json:
                normalized_result = response_json[requested_curie]
                best_id = normalized_result["id"]
                normalized_id = best_id["identifier"]
                if "label" in best_id:
                    normalized_name = best_id["label"]
                normalized_synonyms = set()
                for syn in normalized_result["equivalent_identifiers"]:
                    normalized_synonyms.add(syn["identifier"])
                    if not normalized_name and "label" in syn:
                        normalized_name = syn["label"]

        return normalized_id, normalized_name, normalized_synonyms

    def get_sequence_variant_normalization(self, variant_node: KNode):
        return self.genetics_normalizer.get_sequence_variant_normalization(variant_node.synonyms)

    def precache_sequence_variants_by_batch(self, batch_of_hgvs: list):
        batch_normalizations = self.genetics_normalizer.get_batch_sequence_variant_normalization(batch_of_hgvs)
        with self.cache.get_pipeline() as pipe:
            count = 0
            for hgvs_curie, normalization in batch_normalizations.items():
                self.set_normalization(hgvs_curie, normalization, pipe)
                count += 1

                # Do we want to precache normalization for the CAID key as well since we're already here?
                # For now we don't start with a CAID from other sources so it isn't immediately useful
                # If so we could do something like this:
                #normalized_id, normalized_name, synonyms = normalization
                #
                #caid_curie = None
                #for syn in synonyms:
                #    if syn.startswith('CAID'):
                #        caid_curie = syn
                #        break
                #if caid_curie:
                #    self.set_normalization(caid_curie, normalization, pipe)
                #    count += 1
                if count == 1000:
                    pipe.execute()
                    count = 0
            if count > 0:
                pipe.execute()
