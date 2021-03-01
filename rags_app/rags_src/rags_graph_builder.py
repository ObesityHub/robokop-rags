import logging
import os
import time
from itertools import chain
from typing import List
from dataclasses import dataclass, field

from rags_src.rags_core import *
from rags_src.rags_file_tools import GWASFileReader, MWASFileReader
from rags_src.rags_graph_writer import BufferedWriter
from rags_src.rags_graph_db import RagsGraphDB
from rags_src.rags_project_db_models import RAGsStudy
from rags_src.rags_file_tools import GWASFile, MWASFile
from rags_src.util import LoggingUtil
from rags_src.rags_normalizer import RagsNormalizer

import rags_src.rags_core as rags_core

from robokop_genetics.genetics_services import GeneticsServices, ALL_VARIANT_TO_GENE_SERVICES
from robokop_genetics.genetics_normalization import GeneticsNormalizer


logger = LoggingUtil.init_logging("rags.rags_graph_builder", logging.INFO, format='medium', logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')


@dataclass
class RagsGraphBuilderResults:
    warning_messages: list = field(default_factory=list)
    error_messages: list = field(default_factory=list)
    success_message: str = ""
    success: bool = False


class RAGsGraphBuilder(object):

    def __init__(self,
                 project_id: int,
                 project_name: str,
                 rags_data_directory: str,
                 graph_db: RagsGraphDB,
                 rags_normalizer: RagsNormalizer = None):
        self.project_id = project_id
        self.project_name = project_name
        self.genetics_normalizer = GeneticsNormalizer(use_cache=False)
        self.genetics_services = GeneticsServices(use_cache=False)
        self.writer = BufferedWriter(graph_db)
        self.rags_data_directory = rags_data_directory
        self.rags_normalizer = rags_normalizer if rags_normalizer else RagsNormalizer()
        self.association_relation = 'RO:0002610'
        self.normalized_association_predicate = self.fetch_normalized_association_predicate()

    def write_nodes(self,
                    nodes: list):
        for node in nodes:
            self.writer.write_node(node)
        self.writer.flush()

    def find_significant_hits(self,
                              study: RAGsStudy):

        real_file_path = self.get_real_file_path(study)
        if study.study_type == rags_core.GWAS:
            gwas_file = GWASFile(file_path=real_file_path)
            with GWASFileReader(gwas_file) as gwas_file_reader:
                results = gwas_file_reader.find_significant_hits(study.p_value_cutoff)
        elif study.study_type == rags_core.MWAS:
            mwas_file = MWASFile(file_path=real_file_path)
            with MWASFileReader(mwas_file) as mwas_file_reader:
                results = mwas_file_reader.find_significant_hits(study.p_value_cutoff)
        else:
            error_message = f"Study type ({study.study_type}) not supported - no file reader found."
            logger.warning(error_message)
            results = {"success": False, "error_message": error_message}

        return results

    def process_gwas_variants(self, gwas_hits: List[GWASHit]):

        variant_ids = [hit.original_id for hit in gwas_hits]
        logger.debug(f'Found {len(variant_ids)} sequence variant nodes to normalize. Normalizing...')
        variant_node_failures = []
        variant_node_types = frozenset(self.genetics_normalizer.get_sequence_variant_node_types())
        sequence_variant_normalizations = self.genetics_normalizer.normalize_variants(variant_ids)
        normalized_variant_nodes = []
        for gwas_hit in gwas_hits:
            gwas_hit.normalized = True
            original_id = gwas_hit.original_id
            normalized_info = sequence_variant_normalizations[original_id]
            if normalized_info:
                # sequence variant normalization returns a list of results but assume there is only one item or nothing
                # this is because we always start with unambiguous IDs for RAGs GWAS variants
                normalized_id = normalized_info[0]["id"]
                gwas_hit.normalized_id = normalized_id
                normalized_name = normalized_info[0]["name"]
                gwas_hit.normalized_name = normalized_name
                equivalent_identifiers = normalized_info[0]["equivalent_identifiers"]
            else:
                variant_node_failures.append(original_id)
                normalized_id = original_id
                normalized_name = gwas_hit.original_name
                equivalent_identifiers = set()

            variant_node = RAGsNode(normalized_id,
                                    type=SEQUENCE_VARIANT,
                                    name=normalized_name,
                                    all_types=variant_node_types,
                                    synonyms=equivalent_identifiers)
            normalized_variant_nodes.append(variant_node)

        self.write_nodes(normalized_variant_nodes)
        if variant_node_failures:
            logger.warning(f'Processing GWAS variants, these failed normalization: {", ".join(variant_node_failures)}')
        logger.debug(f'Writing variant nodes complete.')
        """
        logger.debug(f'Finding and writing variant to gene relationships.')
        v_to_gene_results = self.genetics_services.get_variant_to_gene(ALL_VARIANT_TO_GENE_SERVICES, normalized_variant_nodes)
        gene_node_ids = [node.id for (edge, node) in chain.from_iterable(v_to_gene_results.values())]
        gene_normalizations = self.rags_normalizer.get_normalized_nodes(gene_node_ids)

        self.write_nodes(gene_normalizations.values())

        for variant_node_id, results in v_to_gene_results.items():
            # convert the simple edges and nodes to rags objects and write them to the graph
            for (edge, gene_node) in results:
                original_gene_id = gene_node.id
                if gene_normalizations[gene_node.id]:
                    normalized_gene_id = gene_normalizations[gene_node.id].id
                else:
                    normalized_gene_id = original_gene_id

                gene_edge = RAGsEdge(id=None,
                                     subject_id=variant_node_id,
                                     object_id=normalized_gene_id,
                                     original_object_id=original_gene_id,
                                     predicate=edge.predicate,
                                     relation=edge.relation,
                                     ctime=edge.ctime,
                                     provided_by=edge.provided_by,
                                     properties=edge.properties)
                self.writer.write_edge(gene_edge)
                
            logger.debug(f'added {len(results)} variant relationships for {variant_node_id}')
        self.writer.flush()
        
        logger.debug(f'Writing variant to gene relationships complete.')
        """

        return len(gwas_hits)

    def process_gwas_associations(self,
                                  gwas_study: RAGsStudy,
                                  gwas_hits: List[GWASHit]):

        associations_written_count = 0
        missing_variants_count = 0
        p_value_too_high = 0
        relation = self.association_relation
        predicate = self.normalized_association_predicate
        real_file_path = self.get_real_file_path(gwas_study)
        gwas_file = GWASFile(file_path=real_file_path)
        normalized_trait_id = gwas_study.normalized_trait_id if gwas_study.normalized_trait_id else gwas_study.original_trait_id

        unique_gwas_hits = []
        already_added = set()
        for hit in gwas_hits:
            if hit.normalized_id and hit.normalized_id not in already_added:
                unique_gwas_hits.append(hit)
                already_added.add(hit.normalized_id)
            elif not hit.normalized_id and hit.original_id not in already_added:
                unique_gwas_hits.append(hit)
                already_added.add(hit.original_id)

        with GWASFileReader(gwas_file, use_tabix=gwas_file.has_tabix) as gwas_file_reader:

            gwas_associations = map(gwas_file_reader.get_gwas_association_from_file, unique_gwas_hits)
            for gwas_hit, association in zip(unique_gwas_hits, gwas_associations):
                if association:
                    if (gwas_study.max_p_value is None) or (association.p_value <= gwas_study.max_p_value):
                        normalized_variant_id = gwas_hit.normalized_id if gwas_hit.normalized_id else gwas_hit.original_id
                        properties = {'p_value': association.p_value,
                                      'strength': association.beta,
                                      'ctime': int(time.time())}

                        new_edge = RAGsEdge(id=None,
                                            subject_id=normalized_trait_id,
                                            object_id=normalized_variant_id,
                                            original_object_id=gwas_hit.original_id,
                                            predicate=predicate,
                                            relation=relation,
                                            provided_by='RAGS_Builder',
                                            namespace=gwas_study.study_name,
                                            project_id=self.project_id,
                                            project_name=self.project_name,
                                            properties=properties)

                        self.writer.write_edge(new_edge)
                        associations_written_count += 1
                    else:
                        p_value_too_high += 1
                else:
                    missing_variants_count += 1
            if not gwas_study.num_associations:
                gwas_study.num_associations = associations_written_count
            else:
                gwas_study.num_associations += associations_written_count

        if missing_variants_count > 0:
            logger.warning(f'{gwas_study.study_name} had {missing_variants_count} missing variants!')
        if p_value_too_high > 0:
            logger.debug(f'{gwas_study.study_name} had {p_value_too_high} associations with p values that exceeded {gwas_study.max_p_value}!')
        if associations_written_count:
            logger.debug(f'{gwas_study.study_name} had {associations_written_count} new associations written.')
        else:
            logger.debug(f'{gwas_study.study_name} failed to find any new valid associations.')

        self.writer.flush()

        return True

    def process_mwas_metabolites(self, mwas_hits: List[MWASHit]):

        results = RagsGraphBuilderResults()

        metabolite_ids = [hit.original_id for hit in mwas_hits]

        # dictionary of node ID -> RagsNode
        normalized_nodes = self.rags_normalizer.get_normalized_nodes(metabolite_ids)

        nodes_to_write = []
        for mwas_hit in mwas_hits:
            normalized_node = normalized_nodes[mwas_hit.original_id]
            if normalized_node is not None:
                mwas_hit.normalized_id = normalized_node.id
                mwas_hit.normalized_name = normalized_node.name
            else:
                warning = f"Normalization could not find a result for {mwas_hit.original_id}"
                #logger.warning(warning)
                results.warning_messages.append(warning)
                normalized_node = RAGsNode(mwas_hit.original_id,
                                           type=CHEMICAL_SUBSTANCE,
                                           name=mwas_hit.original_name,
                                           all_types=frozenset([ROOT_ENTITY, CHEMICAL_SUBSTANCE]))
            mwas_hit.normalized = True
            nodes_to_write.append(normalized_node)

        self.write_nodes(nodes_to_write)

        results.success = True
        results.success_message = f"Processed {len(mwas_hits)} metabolites."
        return results

    def process_mwas_associations(self,
                                  mwas_study: RAGsStudy,
                                  mwas_hits: List[MWASHit]):

        associations_written_count = 0
        missing_metabolites_count = 0
        p_value_too_high = 0
        relation = self.association_relation
        predicate = self.normalized_association_predicate
        real_file_path = self.get_real_file_path(mwas_study)
        mwas_file = MWASFile(file_path=real_file_path)
        normalized_trait_id = mwas_study.normalized_trait_id if mwas_study.normalized_trait_id else mwas_study.original_trait_id

        unique_mwas_hits = []
        for hit in mwas_hits:
            if hit.original_id not in unique_mwas_hits:
                unique_mwas_hits.append(hit)

        with MWASFileReader(mwas_file) as mwas_file_reader:
            for mwas_hit in unique_mwas_hits:
                association = mwas_file_reader.get_mwas_association_from_file(mwas_hit)
                if association:
                    if (mwas_study.max_p_value is None) or (association.p_value <= mwas_study.max_p_value):
                        normalized_metabolite_id = mwas_hit.normalized_id if mwas_hit.normalized_id else mwas_hit.original_id

                        properties = {'p_value': association.p_value,
                                      'strength': association.beta,
                                      'ctime': int(time.time())}

                        new_edge = RAGsEdge(id=None,
                                            subject_id=normalized_trait_id,
                                            object_id=normalized_metabolite_id,
                                            original_object_id=mwas_hit.original_id,
                                            predicate=predicate,
                                            relation=relation,
                                            provided_by='RAGS_Builder',
                                            namespace=mwas_study.study_name,
                                            project_id=self.project_id,
                                            project_name=self.project_name,
                                            properties=properties)

                        self.writer.write_edge(new_edge)
                        associations_written_count += 1
                    elif mwas_study.max_p_value:
                        p_value_too_high += 1
                else:
                    missing_metabolites_count += 1
            if not mwas_study.num_associations:
                mwas_study.num_associations = associations_written_count
            else:
                mwas_study.num_associations += associations_written_count

        if missing_metabolites_count > 0:
            logger.warning(f'{mwas_study.study_name} had {missing_metabolites_count} missing metabolites!')
        if p_value_too_high > 0:
            logger.warning(f'{mwas_study.study_name} had {p_value_too_high} metabolites with p values that exceeded {mwas_study.max_p_value}!')
        if associations_written_count:
            logger.debug(f'{mwas_study.study_name} had {associations_written_count} new associations written.')
        else:
            logger.info(f'{mwas_study.study_name} failed to find any new valid associations.')

        self.writer.flush()

        return True

    def get_real_file_path(self, study: RAGsStudy):
        return f'{self.rags_data_directory}/{study.file_path}'

    def fetch_normalized_association_predicate(self):
        normalized_edges = self.rags_normalizer.get_normalized_edges([self.association_relation])
        return normalized_edges[self.association_relation]