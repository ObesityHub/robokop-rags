from rags_src.rags_core import RAGsNode
from rags_src.util import LoggingUtil, Text

import logging
import requests
import os

logger = LoggingUtil.init_logging("rags.normalizer", logging.INFO, format='medium', logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')


class RagsNormalizationError(Exception):
    def __init__(self, error_message: str):
        self.message = error_message


class RagsNormalizer(object):

    def __init__(self):
        self.node_normalization_url = os.environ["NODE_NORMALIZATION_ENDPOINT"]
        self.edge_normalization_url = os.environ["EDGE_NORMALIZATION_ENDPOINT"]

        self.cached_normalized_nodes = {}
        self.cached_normalized_predicates = {}

    def get_normalized_edges(self, predicates: list):

        # filter out previously cached normalizations, remove duplicates
        predicates_to_normalize = list(set([predicate for predicate in predicates if predicate not in self.cached_normalized_predicates]))

        # split the remaining predicates into batches of 1000
        batches = [predicates_to_normalize[i: i + 1000] for i in range(0, len(predicates_to_normalize), 1000)]

        # make a request for each batch of predicates
        for batch in batches:
            r = requests.get(self.edge_normalization_url, params={'predicate': batch})
            if r.status_code == 200:
                response_json = r.json()
                # for each predicate store the response information or None in cached_normalized_predicates
                for predicate in batch:
                    try:
                        normalization_response = response_json[predicate]
                    except KeyError:
                        error_message = f'Edge Normalization returned 200 but was missing an entry for {predicate}: {r.url}'
                        logger.error(error_message)
                        raise RagsNormalizationError(error_message)
                    if normalization_response:
                        normalized_predicate = normalization_response['identifier']
                        self.cached_normalized_predicates[predicate] = normalized_predicate
                    else:
                        # if there was no good response, store None instead
                        self.cached_normalized_predicates[predicate] = None
            elif r.status_code == 404:
                # 404 means none of them were found - store None for all of them
                for predicate in batch:
                    self.cached_normalized_predicates[predicate] = None
            else:
                # this is an abnormal response, bail
                error_message = f'Edge Normalization returned a non-200 response({r.status_code}) for {len(batch)} predicates.. {r.json()}'
                logger.error(error_message)
                raise RagsNormalizationError(error_message)

        return self.cached_normalized_predicates

    def get_normalized_nodes(self, node_ids: list):

        # filter out previously cached normalizations, remove duplicates
        ids_to_normalize = list(set([node_id for node_id in node_ids if node_id not in self.cached_normalized_nodes]))

        # split the remaining node ids into batches of 1000
        batches = [ids_to_normalize[i: i + 1000] for i in range(0, len(ids_to_normalize), 1000)]

        # make a request for each batch of ids
        for batch in batches:
            # set 'curies' http post parameter to the current batch of node ids
            payload = {'curies': batch}
            r = requests.post(self.node_normalization_url, json=payload)
            if r.status_code == 200:
                response_json = r.json()
                # for each node id store the response information or None in cached_normalized_nodes
                for node_id in batch:
                    try:
                        normalization_response = response_json[node_id]
                    except KeyError:
                        error_message = f'Node Normalization returned 200 but was missing an entry for {node_id}: {r.url}'
                        logger.error(error_message)
                        raise RagsNormalizationError(error_message)
                    if normalization_response:
                        #logger.warning(f'found response for {node_id}')
                        normalized_node = self.parse_normalization_json(normalization_response)
                        self.cached_normalized_nodes[node_id] = normalized_node
                    else:
                        #logger.warning(f'found no norm response for {node_id}')
                        # if there was no good response, store None instead
                        self.cached_normalized_nodes[node_id] = None
            elif r.status_code == 404:
                # 404 means none of them were found - store None for all of them
                for node_id in batch:
                    logger.warning(f'found no norm response for {node_id}')
                    self.cached_normalized_nodes[node_id] = None
            else:
                # this is an abnormal response, bail
                error_message = f'Node Normalization returned a non-200 response({r.status_code}) for {len(batch)} nodes.. {r.json()}'
                logger.error(error_message)
                raise RagsNormalizationError(error_message)

        return self.cached_normalized_nodes

    def parse_normalization_json(self, normalization_result):
        best_id = normalization_result["id"]
        normalized_id = best_id["identifier"]
        if "label" in best_id:
            normalized_name = best_id["label"]
        else:
            normalized_name = ""

        normalized_synonyms = set()
        for syn in normalization_result["equivalent_identifiers"]:
            normalized_synonyms.add(syn["identifier"])
            if not normalized_name and "label" in syn:
                normalized_name = syn["label"]

        if not normalized_name:
            normalized_name = Text.un_curie(normalized_id)

        normalized_types = frozenset(normalization_result["type"])

        normalized_node = RAGsNode(normalized_id,
                                   type=None,
                                   name=normalized_name,
                                   synonyms=normalized_synonyms,
                                   all_types=normalized_types)
        return normalized_node

