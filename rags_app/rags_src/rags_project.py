
from rags_src.rags_graph_builder import RagsGraphBuilder
from rags_src.rags_validation import RagsValidator
from rags_src.rags_graph_db import RagsGraphDB
from rags_src.rags_project_db import RagsProjectDB
from rags_src.util import LoggingUtil
from rags_src.rags_cache import Cache
from rags_src.rags_normalizer import RagsNormalizer
from rags_src.rags_core import Project, GWAS, MWAS
import logging
import os

logger = LoggingUtil.init_logging("rags.projects", logging.INFO, format='medium', logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')

validation_logger = LoggingUtil.init_logging("rags.project_validation", logging.INFO, format='medium', logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')


class RagsProject:

    def __init__(self, project: Project, project_db: RagsProjectDB):
        self.project_id = project.id
        self.project_name = project.name
        self.project_db = project_db

        # Lazy instantiation
        self.all_rags = None
        self.all_hits = None
        self.rags_builder = None
        self.rags_validator = None

    def init_builder(self):
        if not self.rags_builder:
            rags_cache = Cache(
                redis_host=os.environ["RAGS_CACHE_HOST"],
                redis_port=os.environ["RAGS_CACHE_PORT"],
                redis_db=os.environ["RAGS_CACHE_DB"],
                redis_password=os.environ["RAGS_CACHE_PASSWORD"])
            self.rags_builder = RagsGraphBuilder(self.project_id,
                                                 self.project_name,
                                                 RagsGraphDB(),
                                                 rags_cache)

    def prep_rags(self):
        logger.info('About to prep rags!')
        self.init_builder()

        all_rags = self.project_db.get_rags(self.project_id)
        num_rags = len(all_rags)
        for rag_counter, rag in enumerate(all_rags, 1):
            if not rag.searched:
                logger.info(f'Finding significant hits in file {rag_counter} of {num_rags}.')
                success, hits_container, num_hits = self.rags_builder.find_significant_hits(rag)
                if success:
                    logger.info(f'Found {num_hits} significant hits for {rag.rag_name}.')
                    rag.searched = True
                    rag.num_hits = num_hits
                    self.project_db.save_hits(self.project_id, rag, hits_container)
                    self.project_db.update_rag(rag)
                else:
                    # TODO informative error messages should displayed to the user somehow
                    logger.error(f'Error finding significant hits in {rag.rag_name}.')
            else:
                logger.info(f'Significant hits already found for {rag.rag_name}.')

        return {"success": True, "success_message": "All rags searched for significant hits."}

    def build_rags(self):
        logger.info('About to build rags!')
        self.init_builder()

        # Normalize, cache, and process everything needed for the sequence variants.
        # Write all of that to the graph.
        unprocessed_gwas_hits = self.project_db.get_unprocessed_gwas_hits(self.project_id)
        if unprocessed_gwas_hits:
            logger.info('About to process sequence variants!')
            num_processed_gwas_hits = self.rags_builder.process_gwas_variants(unprocessed_gwas_hits)
            logger.info(f'{num_processed_gwas_hits} new sequence variants processed and added to the graph.')
            # the process_gwas_variants function may change GWASHit ORM objects which would be committed to the DB here
            self.project_db.commit_orm_transactions()
        else:
            logger.info(f'No unprocessed sequence variants found for {self.project_id}.')

        # Normalize, cache, and process everything needed for the metabolites.
        # Write all of that to the graph.
        metabolite_hits = self.project_db.get_unprocessed_mwas_hits(self.project_id)
        if metabolite_hits:
            logger.info('About to process metabolites!')
            processed_mwas_hits = self.rags_builder.process_mwas_metabolites(metabolite_hits)
            logger.info(f'{len(processed_mwas_hits)} new sequence variants processed and added to the graph.')
            # the process_mwas_metabolites function may change MWASHit ORM objects which would be committed to the DB here
            self.project_db.commit_orm_transactions()
        else:
            logger.info(f'No unprocessed metabolites found for {self.project_id}.')


        # variant nodes are already written
        # next go into the files and find/write the associations
        all_rags = self.project_db.get_rags(self.project_id)
        all_gwas_hits = self.project_db.get_all_gwas_hits(self.project_id)
        unprocessed_gwas_hits = self.project_db.get_unprocessed_gwas_hits(self.project_id)
        all_mwas_hits = self.project_db.get_all_mwas_hits(self.project_id)
        unprocessed_mwas_hits = self.project_db.get_unprocessed_mwas_hits(self.project_id)

        total_num_rags = len(all_rags)
        for rag_counter, rag in enumerate(all_rags, 1):
            logger.info(f'Starting rag associations {rag_counter} of {total_num_rags}: {rag.rag_name}')
            if rag.rag_type == MWAS:
                if rag.written:
                    self.rags_builder.process_mwas_associations(rag, unprocessed_mwas_hits)
                else:
                    self.rags_builder.process_mwas_associations(rag, all_mwas_hits)

            elif rag.rag_type == GWAS:
                if rag.written:
                    # it's been written previously, only add the new associations
                    self.rags_builder.process_gwas_associations(rag, unprocessed_gwas_hits)
                else:
                    # otherwise write all of the associations
                    self.rags_builder.process_gwas_associations(rag, all_gwas_hits)
            rag.written = True

        for gwas_hit in unprocessed_gwas_hits:
            gwas_hit.written = True

        for mwas_hit in unprocessed_mwas_hits:
            mwas_hit.written = True

        self.project_db.commit_orm_transactions()

        summary_output = f'Creating gwas graph complete. Summary:\n'
        summary_output += f'Project: {self.project_id}\n'
        #summary_output += f'Rags(new/total): {len(new_gwas_builds)}/{total_num_gwas}\n'
        #summary_output += f'New Variants: {len(new_variant_labled_ids)}\n'
        #summary_output += f'Bad/Missing builds: {num_bad_rags}\n'
        logger.info(summary_output)

        return {"success": True, "success_message": "The graph was built successfully."}

    def init_validator(self):
        if not self.rags_validator:
            self.rags_validator = RagsValidator(self.graph_db, self.normalizer)

    def validate_project(self, verbose=False):
        logger.info(f'Running validation for all builds in {self.project_id}')

        self.init_validator()

        all_good = True
        for gwas_build in self.all_gwas_builds.values():
            validation_info = self.rags_validator.validate_associations(self.project_id, gwas_build,
                                                                        self.all_significant_variants,
                                                                        verbose=verbose)
            output = f'Validation for {gwas_build.build_name}: {validation_info.message}'
            if verbose:
                output += f'\nDetails: {validation_info.details}'

            validation_logger.info(output)

            if not validation_info.success:
                all_good = False
        return all_good


    #def crawl_project(self):
    #    node_ids = []
    #    for variant in self.all_significant_variants.iterate_all_variants():
    #        node_ids.append(variant.real_id)
    #
    #    poolrun(node_types.SEQUENCE_VARIANT, node_types.GENE, self.rosetta, identifier_list=labeled_ids)



