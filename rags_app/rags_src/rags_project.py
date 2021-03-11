
from rags_src.rags_graph_builder import RAGsGraphBuilder
from rags_src.rags_validation import RagsValidator
from rags_src.rags_normalizer import RagsNormalizer
from rags_src.rags_graph_db import RagsGraphDB
from rags_src.rags_project_db import RagsProjectDB
from rags_src.util import LoggingUtil
from rags_src.rags_core import RAGsNode, GWAS, MWAS, ROOT_ENTITY, RAGS_ERROR_SEARCHING, RAGS_ERROR_BUILDING, SEQUENCE_VARIANT
from dataclasses import dataclass
import logging
import os

logger = LoggingUtil.init_logging("rags.projects", logging.INFO, format='medium', logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')

validation_logger = LoggingUtil.init_logging("rags.project_validation", logging.INFO, format='medium', logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')


@dataclass
class RagsProjectResults:
    warning_messages: list = None
    error_messages: list = None
    success_message: str = ""
    success: bool = False

    def set_warning_message(self, warning_message: str):
        if not self.warning_messages:
            self.warning_messages = [warning_message]
        else:
            self.warning_messages.append(warning_message)

    def set_error_message(self, error_message: str):
        if not self.error_messages:
            self.error_messages = [error_message]
        else:
            self.error_messages.append(error_message)


class RagsProjectManager:

    def __init__(self, project_id: str, project_name: str, project_db: RagsProjectDB):
        self.project_id = project_id
        self.project_name = project_name
        self.project_db = project_db

        self.rags_normalizer = RagsNormalizer()
        self.rags_graph_db = RagsGraphDB()

        rags_data_directory = os.environ["RAGS_DATA_DIR"]

        self.rags_builder = RAGsGraphBuilder(self.project_id,
                                             self.project_name,
                                             rags_data_directory,
                                             self.rags_graph_db)

    def process_traits(self, force_rebuild: bool = False):
        results = RagsProjectResults()

        all_studies = self.project_db.get_all_studies(self.project_id)
        if not force_rebuild:
            studies_that_need_normalization = [study for study in all_studies if not study.trait_normalized]
        else:
            studies_that_need_normalization = all_studies
        trait_ids_for_normalization = [study.original_trait_id for study in studies_that_need_normalization]

        # dictionary of node ID -> RagsNode
        normalized_nodes = self.rags_normalizer.get_normalized_nodes(trait_ids_for_normalization)

        nodes_to_write = []
        norm_failures = []
        for study in studies_that_need_normalization:
            normalized_node = normalized_nodes[study.original_trait_id]
            if normalized_node is not None:
                study.normalized_trait_id = normalized_node.id
                study.normalized_trait_label = normalized_node.name
            else:
                norm_failures.append(study.original_trait_id)
                normalized_node = RAGsNode(study.original_trait_id,
                                           study.original_trait_type,
                                           name=study.original_trait_label,
                                           all_types=frozenset([ROOT_ENTITY, study.original_trait_type]))
            study.trait_normalized = True
            nodes_to_write.append(normalized_node)

        if norm_failures:
            warning = f"Normalization could not find a result for these traits: {', '.join(norm_failures)}"
            results.set_warning_message(warning)
            logger.warning(warning)

        self.rags_builder.write_nodes(nodes_to_write)
        self.project_db.commit_orm_transactions()

        results.success = True
        results.success_message = "Traits normalized and written to the graph."
        return results

    def search_studies(self):
        logger.info('Searching RAGs files for significant hits...')
        results = RagsProjectResults()
        all_studies = self.project_db.get_all_studies(self.project_id)
        studies_to_search = [study for study in all_studies if not study.searched]
        search_failures = []
        for i, study in enumerate(studies_to_search, start=1):
            logger.debug(f'Searching for significant hits in study {i} of {len(studies_to_search)}: {study.study_name}')
            hits_results = self.rags_builder.find_significant_hits(study)
            if hits_results["success"]:
                hits_container = hits_results["hits_container"]
                self.project_db.save_hits(self.project_id, study, hits_container, delay_commit=True)

                hit_counter = hits_results["hit_counter"]
                study.searched = True
                study.num_hits = hit_counter
                self.project_db.clear_study_errors_by_type(study.id,
                                                           RAGS_ERROR_SEARCHING,
                                                           delay_commit=True)
                logger.debug(f'Found {hit_counter} significant hits for {study.study_name}.')
            else:
                study.searched = False
                self.project_db.create_study_error(study.id,
                                                   RAGS_ERROR_BUILDING,
                                                   hits_results["error_message"],
                                                   delay_commit=True)
                search_failures.append(study.study_name)
            # go ahead and commit in the middle of the session because these take a while
            # if funky things happen with the rag session objects, check here..
            self.project_db.commit_orm_transactions()

        if not search_failures:
            results.success = True
            results.success_message = "Studies searched for significant hits."
        else:
            results.success = False
            error_message = f"Error searching for significant hits in these studies: {', '.join(search_failures)}"
            results.set_error_message(error_message)

        return results

    def build_rags(self, force_rebuild: bool = False):

        results = RagsProjectResults()

        logger.info('Normalizing and writing hits to the graph...')
        self.build_hits(force_rebuild)

        # next go into the files and find/write the associations
        logger.info('Writing associations to the graph...')
        self.build_associations(force_rebuild)

        logger.info(f'Building RAGs complete for project: {self.project_id}')

        results.success = True
        results.success_message = "The graph was built successfully."

        return results

    def build_hits(self, force_rebuild: bool = False):
        # Normalize and process everything needed for the sequence variants.
        # Write all of that to the graph.
        if force_rebuild:
            unprocessed_gwas_hits = self.project_db.get_all_gwas_hits(self.project_id)
        else:
            unprocessed_gwas_hits = self.project_db.get_unprocessed_gwas_hits(self.project_id)

        if unprocessed_gwas_hits:
            logger.debug('About to process sequence variants!')
            self.rags_builder.process_gwas_variants(unprocessed_gwas_hits)
            logger.debug(f'{len(unprocessed_gwas_hits)} new sequence variants processed and added to the graph.')
            # the process_gwas_variants function may change GWASHit ORM objects which would be committed to the DB here
            self.project_db.commit_orm_transactions()
        else:
            logger.debug(f'No unprocessed sequence variants found for {self.project_id}.')

        # Normalize and process everything needed for the metabolites.
        # Write all of that to the graph.
        if force_rebuild:
            unprocessed_metabolite_hits = self.project_db.get_all_mwas_hits(self.project_id)
        else:
            unprocessed_metabolite_hits = self.project_db.get_unprocessed_mwas_hits(self.project_id)

        if unprocessed_metabolite_hits:
            logger.debug('About to process metabolites!')
            self.rags_builder.process_mwas_metabolites(unprocessed_metabolite_hits)
            logger.debug(f'{len(unprocessed_metabolite_hits)} new metabolites processed and added to the graph.')
            # the process_mwas_metabolites function may change MWASHit ORM objects which would be committed to the DB here
            self.project_db.commit_orm_transactions()
        else:
            logger.debug(f'No unprocessed metabolites found for {self.project_id}.')

    def build_associations(self, force_rebuild: bool = False):
        all_studies = self.project_db.get_all_studies(self.project_id)
        all_gwas_hits = None
        all_mwas_hits = None
        unwritten_gwas_hits = self.project_db.get_unwritten_gwas_hits(self.project_id)
        unwritten_mwas_hits = self.project_db.get_unwritten_mwas_hits(self.project_id)
        logger.debug(f'Building associations for {len(unwritten_gwas_hits)} gwas hits and {len(unwritten_mwas_hits)} mwas hits.')
        for i, study in enumerate(all_studies, 1):
            if study.searched:
                logger.info(f'Building associations for study {i} of {len(all_studies)}: {study.study_name}')
                if study.study_type == MWAS:
                    if study.written and not force_rebuild:
                        # it's been written previously, only add the new associations
                        self.rags_builder.process_mwas_associations(study, unwritten_mwas_hits)
                    else:
                        # otherwise write all of the associations
                        if all_mwas_hits is None:
                            all_mwas_hits = self.project_db.get_all_mwas_hits(self.project_id)
                        self.rags_builder.process_mwas_associations(study, all_mwas_hits)

                elif study.study_type == GWAS:
                    if study.written and not force_rebuild:
                        # it's been written previously, only add the new associations
                        self.rags_builder.process_gwas_associations(study, unwritten_gwas_hits)
                    else:
                        # otherwise write all of the associations
                        if all_gwas_hits is None:
                            all_gwas_hits = self.project_db.get_all_gwas_hits(self.project_id)
                        self.rags_builder.process_gwas_associations(study, all_gwas_hits)
                study.written = True
            else:
                logger.info(f'Skipping associations for study: {study.study_name} (due to an error in the search phase)')

        if unwritten_gwas_hits:
            for gwas_hit in unwritten_gwas_hits:
                gwas_hit.written = True

        if unwritten_mwas_hits:
            for mwas_hit in unwritten_mwas_hits:
                mwas_hit.written = True

        self.project_db.commit_orm_transactions()

    def annotate_hits(self):

        results = RagsProjectResults()

        normalized_association_predicate = self.rags_builder.normalized_association_predicate
        # TODO the variant node type and nearby variant edge type should be normalized dynamically maybe
        query = f'MATCH (v:`{SEQUENCE_VARIANT}`)<-[:`{normalized_association_predicate}`]-() with distinct v WHERE NOT (v)-[:`biolink:is_nearby_variant_of`]-() return v.id as id, v.equivalent_identifiers as equivalent_identifiers'
        variants_for_annotation = self.rags_graph_db.custom_read_query(query)

        if variants_for_annotation:
            logger.info(f'Found {len(variants_for_annotation)} variants that need genes.')
            self.rags_builder.add_genes_to_variants(variants_for_annotation)
            results.success_message = f"Annotated {len(variants_for_annotation)} variants."
        else:
            logger.info(f'Found no variants that need genes in the graph.')
            results.success_message = f"Found no variants that need genes in the graph."

        # TODO catch normalization or graph exceptions and return better errors
        results.success = True
        return results


    def validate_project(self):
        logger.info(f'Running validation for all builds in {self.project_id}')

        if not self.rags_validator:
            self.rags_validator = RagsValidator(self.rags_graph_db)
        all_good = True
        all_rags = self.project_db.get_rags(self.project_id)
        #num_gwas_hits = self.project_db.get_all_gwas_hits(self.project_id)
        #num_mwas_hits = self.project_db.get_all_mwas_hits(self.project_id)

        for rag in all_rags:
            num_associations = rag.num_associations
            if num_associations:
                validation_info = self.rags_validator.validate_associations(self.project_id,
                                                                            rag,
                                                                            num_associations)
                if not validation_info['success']:
                    all_good = False
            else:
                logger.info(f'In validation: No associations found for rag {rag.rag_name}.')

        return all_good
