import logging
import os
import time
from typing import List

from rags_src.rags_core import *
from rags_src.rags_file_tools import GWASFileReader, MWASFileReader, GWASFile, MWASFile
from rags_src.rags_graph_writer import BufferedWriter
from rags_src.rags_graph_db import RagsGraphDB
from rags_src.rags_project_db_models import RAGsStudy
from rags_src.rags_normalizer import RagsNormalizer
from rags_src.rags_variant_annotation import SequenceVariantAnnotator
from rags_src.util import LoggingUtil

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
        if study.study_type == GWAS:
            gwas_file = GWASFile(file_path=real_file_path, has_tabix=study.has_tabix)
            with GWASFileReader(gwas_file) as gwas_file_reader:
                results = gwas_file_reader.find_significant_hits(study.p_value_cutoff)
        elif study.study_type == MWAS:
            mwas_file = MWASFile(file_path=real_file_path)
            with MWASFileReader(mwas_file) as mwas_file_reader:
                results = mwas_file_reader.find_significant_hits(study.p_value_cutoff)
        else:
            error_message = f"Study type ({study.study_type}) not supported - no file reader found."
            logger.warning(error_message)
            results = {"success": False, "error_message": error_message}

        return results

    def process_gwas_variants(self, gwas_hits: List[GWASHit]):

        variant_ids = list(set([hit.original_id for hit in gwas_hits]))
        logger.info(f'Found {len(variant_ids)} sequence variant nodes to normalize. Normalizing...')
        variant_norm_failures = []
        variant_norm_missing = []
        variant_node_types = frozenset(self.genetics_normalizer.get_sequence_variant_node_types())
        sequence_variant_normalizations = self.genetics_normalizer.normalize_variants(variant_ids)
        normalized_variant_nodes = []
        # this looks like we might write duplicates but we need to update all of the gwas hit models in the DB
        # the graph writer prevents the duplicate node writes if they occur
        for gwas_hit in gwas_hits:
            gwas_hit.normalized = True
            original_id = gwas_hit.original_id
            normalization_response = None
            if len(sequence_variant_normalizations[original_id]) > 0:
                normalization_response = sequence_variant_normalizations[original_id][0]
            if normalization_response and 'id' in normalization_response:
                # sequence variant normalization returns a list of results but assume there is only one item or nothing
                # this is because we always start with unambiguous IDs for RAGs GWAS variants
                variant_node_id = normalization_response["id"]
                gwas_hit.normalized_id = variant_node_id
                variant_node_name = normalization_response["name"]
                gwas_hit.normalized_name = variant_node_name
                equivalent_identifiers = normalization_response["equivalent_identifiers"]
            else:
                if normalization_response:
                    variant_norm_failures.append(original_id)
                else:
                    variant_norm_missing.append(original_id)
                variant_node_id = original_id
                variant_node_name = gwas_hit.original_name
                equivalent_identifiers = set()

            variant_node = RAGsNode(variant_node_id,
                                    type=SEQUENCE_VARIANT,
                                    name=variant_node_name,
                                    all_types=variant_node_types,
                                    synonyms=equivalent_identifiers)
            normalized_variant_nodes.append(variant_node)

        self.write_nodes(normalized_variant_nodes)
        if variant_norm_failures:
            logger.warning(f'Processing GWAS variants, these failed normalization: {", ".join(variant_norm_failures)}')
        if variant_norm_missing:
            logger.warning(f'Processing GWAS variants, these were missing normalization responses: {", ".join(variant_norm_missing)}')
        logger.info(f'Writing variant nodes complete.')

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
        gwas_file = GWASFile(file_path=real_file_path, has_tabix=gwas_study.has_tabix)
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

        with GWASFileReader(gwas_file) as gwas_file_reader:
            creation_time = int(time.time())
            logger.info(f'Reading {len(unique_gwas_hits)} GWAS associations from file!')
            gwas_associations = map(gwas_file_reader.get_gwas_association_from_file, unique_gwas_hits)
            logger.info(f'Building GWAS associations and writing to graph!')
            for gwas_hit, association in zip(unique_gwas_hits, gwas_associations):
                if association:
                    if (gwas_study.max_p_value is None) or (association.p_value <= gwas_study.max_p_value):
                        normalized_variant_id = gwas_hit.normalized_id if gwas_hit.normalized_id else gwas_hit.original_id
                        properties = {'p_value': association.p_value,
                                      'strength': association.beta,
                                      'ctime': creation_time}

                        new_edge = RAGsEdge(id=None,
                                            subject_id=normalized_trait_id,
                                            object_id=normalized_variant_id,
                                            original_object_id=gwas_hit.original_id,
                                            predicate=predicate,
                                            relation=relation,
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

    def add_genes_to_variants(self, variants: list):

        logger.debug(f'Finding gene relationships.')

        variant_nodes = [RAGsNode(v["id"], SEQUENCE_VARIANT, None, synonyms=v["equivalent_identifiers"]) for v in variants]

        variant_annotator = SequenceVariantAnnotator()
        annotation_results = variant_annotator.get_variant_annotations(variant_nodes)
        annotation_object_nodes = annotation_results['objects']
        annotation_edges = annotation_results['edges']

        logger.debug(f'Normalizing genes from annotation..')
        gene_node_ids = [node.id for node in annotation_object_nodes]
        gene_normalizations = self.rags_normalizer.get_normalized_nodes(gene_node_ids)

        logger.debug(f'Normalizing predicates from annotation..')
        predicates = [edge.relation for edge in annotation_edges]
        predicate_normalizations = self.rags_normalizer.get_normalized_edges(predicates)

        successfully_normalized_genes = [node for node in gene_normalizations.values() if node is not None]
        logger.info(f'Writing {len(successfully_normalized_genes)} genes.')
        self.write_nodes(successfully_normalized_genes)
        self.writer.flush()

        already_written_edges = set()
        logger.info(f'Writing {len(annotation_edges)} variant to gene relationships.')
        for edge in annotation_edges:
            normalized_predicate = predicate_normalizations[edge.predicate]
            gene_node_id = edge.original_object_id
            if gene_normalizations[gene_node_id]:
                normalized_gene_id = gene_normalizations[gene_node_id].id
                edge_key = f'{edge.subject_id}{normalized_gene_id}{normalized_predicate}'
                if edge_key not in already_written_edges:
                    gene_edge = RAGsEdge(id=None,
                                         subject_id=edge.subject_id,
                                         object_id=normalized_gene_id,
                                         original_object_id=gene_node_id,
                                         predicate=normalized_predicate,
                                         relation=edge.relation,
                                         provided_by=edge.provided_by,
                                         properties=edge.properties)
                    self.writer.write_edge(gene_edge)
                    already_written_edges.add(edge_key)

        self.writer.flush()
        logger.info(f'Writing variant to gene relationships complete.')

    def process_mwas_metabolites(self, mwas_hits: List[MWASHit]):

        results = RagsGraphBuilderResults()

        metabolite_ids = list(set([hit.original_id for hit in mwas_hits]))

        # dictionary of node ID -> RagsNode
        normalized_nodes = self.rags_normalizer.get_normalized_nodes(metabolite_ids)

        nodes_to_write = []
        metabolite_norm_failures = []
        for mwas_hit in mwas_hits:
            normalized_node = normalized_nodes[mwas_hit.original_id]
            if normalized_node is not None:
                mwas_hit.normalized_id = normalized_node.id
                mwas_hit.normalized_name = normalized_node.name
            else:
                warning = f"Normalization could not find a result for {mwas_hit.original_id}"
                #logger.warning(warning)
                metabolite_norm_failures.append(mwas_hit.original_id)
                results.warning_messages.append(warning)
                normalized_node = RAGsNode(mwas_hit.original_id,
                                           type=CHEMICAL_SUBSTANCE,
                                           name=mwas_hit.original_name,
                                           all_types=frozenset([ROOT_ENTITY, CHEMICAL_SUBSTANCE]))
            mwas_hit.normalized = True
            nodes_to_write.append(normalized_node)

        self.write_nodes(nodes_to_write)

        if metabolite_norm_failures:
            logger.warning(f'Processing MWAS metabolites, these failed normalization: {", ".join(metabolite_norm_failures)}')

        results.success = True
        results.success_message = f"Processed {len(metabolite_ids)} metabolites."
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
            creation_time = int(time.time())
            for mwas_hit in unique_mwas_hits:
                association = mwas_file_reader.get_mwas_association_from_file(mwas_hit)
                if association:
                    if (mwas_study.max_p_value is None) or (association.p_value <= mwas_study.max_p_value):
                        normalized_metabolite_id = mwas_hit.normalized_id if mwas_hit.normalized_id else mwas_hit.original_id

                        properties = {'p_value': association.p_value,
                                      'strength': association.beta,
                                      'ctime': creation_time}

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

