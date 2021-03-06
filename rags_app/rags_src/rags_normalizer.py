from rags_src.rags_cache import Cache
from rags_src.graph_components import KNode
from rags_src.util import LoggingUtil, Text

import logging
import requests
import os

logger = LoggingUtil.init_logging("rags.normalizer", logging.INFO, format='medium', logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')


class RagsNormalizer(object):

    def __init__(self, cache: Cache = None):
        self.node_normalization_url = os.environ["NODE_NORMALIZATION_ENDPOINT"]
        self.cache = cache if cache else Cache(
                redis_host=os.environ["RAGS_CACHE_HOST"],
                redis_port=os.environ["RAGS_CACHE_PORT"],
                redis_db=os.environ["RAGS_CACHE_DB"],
                redis_password=os.environ["RAGS_CACHE_PASSWORD"])

    def set_normalization(self, node_id: str, normalization: tuple, cache_pipe=None):
        key = f"normalization({node_id})"
        self.cache.set(key, normalization, cache_pipe)

    def get_normalization(self, node_id: str):
        key = f"normalization({node_id})"
        return self.cache.get(key)

    def normalize(self, node: KNode):
        # Check the cache. If it's not in there, go find it.
        normalization = self.get_normalization(node.id)
        if normalization is not None:
            # logger.info(f"cache hit: {key} {normalization}")
            pass
        else:
            normalization = self.query_node_normalization(node.id)
            self.set_normalization(node.id, normalization)

        if normalization and normalization != (None, None, None):
            normalized_id, normalized_name, synonyms = normalization
            node.id = normalized_id
            node.name = normalized_name
            node.synonyms = synonyms
        else:
            if not node.name:
                node.name = Text.un_curie(node.id)

    def query_node_normalization(self, requested_curie: str):
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
                normalized_name = Text.un_curie(normalized_id)
                if "label" in best_id:
                    normalized_name = best_id["label"]
                normalized_synonyms = set()
                for syn in normalized_result["equivalent_identifiers"]:
                    normalized_synonyms.add(syn["identifier"])
                    if not normalized_name and "label" in syn:
                        normalized_name = syn["label"]
            else:
                normalized_id, normalized_name, normalized_synonyms = None, None, None

        return normalized_id, normalized_name, normalized_synonyms
