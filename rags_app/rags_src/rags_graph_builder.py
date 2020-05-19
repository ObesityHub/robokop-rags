from rags_src.rags_file_tools import GWASFileReader, MWASFileReader
from rags_src.rags_core import RAG

from rags_src.graph_components import KNode, KEdge, LabeledID
from rags_src.rags_graph_writer import BufferedWriter
from rags_src.rags_graph_db import RagsGraphDB
from rags_src.rags_file_tools import GWASFile, MWASFile
from rags_src.util import LoggingUtil
from rags_src.rags_cache import Cache
from rags_src.rags_normalizer import RagsNormalizer

import rags_src.node_types as node_types
import rags_src.rags_core as rags_core
from rags_src.rags_core import GWASHit, MWASHit

from robokop_genetics.genetics_services import GeneticsServices, MYVARIANT, ALL_VARIANT_TO_GENE_SERVICES

from typing import List
import logging
import os
import time

logger = LoggingUtil.init_logging("rags.rags_graph_builder", logging.INFO, format='medium', logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')


class RagsGraphBuilder(object):

    def __init__(self, project_id: str, project_name: str, graph_db: RagsGraphDB, cache: Cache):
        self.project_id = project_id
        self.project_name = project_name
        self.cache = cache
        self.normalizer = RagsNormalizer(cache)
        self.genetics_services = GeneticsServices()
        self.writer = BufferedWriter(graph_db)
        #self.concept_model = rosetta.type_graph.concept_model

    def find_significant_hits(self,
                              rag: RAG):
        success, hit_container, num_found = False, None, None
        if rag.rag_type == rags_core.GWAS:
            gwas_file = GWASFile(rag.file_path)
            with GWASFileReader(gwas_file) as gwas_file_reader:
                success, hit_container, num_found = gwas_file_reader.find_significant_hits(rag.p_value_cutoff)
        elif rag.rag_type == rags_core.MWAS:
            mwas_file = MWASFile(rag.file_path)
            with MWASFileReader(mwas_file) as mwas_file_reader:
                success, hit_container, num_found = mwas_file_reader.find_significant_hits(rag.p_value_cutoff)

        return success, hit_container, num_found

    def process_gwas_variants(self, gwas_hits: List[GWASHit]):
        batch_of_hgvs = []
        for gwas_hit in gwas_hits:
            batch_of_hgvs.append(gwas_hit.hgvs)
        self.normalizer.precache_sequence_variants_by_batch(batch_of_hgvs)

        processed_nodes = []
        for gwas_hit in gwas_hits:
            curie_hgvs = f'HGVS:{gwas_hit.hgvs}'
            logger.info(f'processing {curie_hgvs}')
            variant_node = KNode(curie_hgvs, type=node_types.SEQUENCE_VARIANT)
            self.normalizer.normalize(variant_node)
            logger.info(f'normalized to {variant_node.id}')

            self.writer.write_node(variant_node)

            # important - the real curie being stored is what signifies the variant has been processed
            gwas_hit.curie = variant_node.id

            processed_nodes.append(variant_node)

        self.precache_variant_knowledge_by_batch(processed_nodes)
        for node in processed_nodes:
            self.process_gwas_variant_knowledge(node)

        self.writer.flush()

        return len(processed_nodes)

    def process_gwas_variant_knowledge(self, variant_node: KNode):
        logger.info(f'processing variant relationships for {variant_node.id}')

        all_results = []
        for service_key in ALL_VARIANT_TO_GENE_SERVICES:
            cache_key = f'{service_key}.sequence_variant_to_gene({variant_node.id})'
            results = self.cache.get(cache_key)
            if results is None:
                results = self.genetics_services.get_variant_to_gene(service_key,
                                                                     variant_node.id,
                                                                     variant_node.synonyms)
                self.cache.set(cache_key, results)
            all_results.extend(results)

        # convert the simple edges and nodes to rags objects and write them to the graph
        for (edge, node) in all_results:
            gene_node = KNode(id=node.id, type=node.type, name=node.name, properties=node.properties)
            self.normalizer.normalize(gene_node)
            self.writer.write_node(gene_node)

            predicate = LabeledID(identifier=edge.predicate_id, label=edge.predicate_label)
            gene_edge = KEdge(source_id=edge.source_id,
                              target_id=edge.target_id,
                              provided_by=edge.provided_by,
                              ctime=edge.ctime,
                              original_predicate=predicate,
                              standard_predicate=predicate,
                              input_id=edge.input_id,
                              namespace=None,
                              project_id=self.project_id,
                              project_name=self.project_name,
                              properties=edge.properties)
            self.writer.write_edge(gene_edge)
        logger.info(f'added {len(all_results)} variant relationships for {variant_node.id}')

    # batch precache any sequence variant data
    def precache_variant_knowledge_by_batch(self, variant_nodes: list):
        # init the return value
        ret_val = None
        try:
            for variant_node in variant_nodes:
                # check if myvariant key exists in cache, otherwise add it to buffer for batch processing
                cache_results = self.cache.get(f'{MYVARIANT}.sequence_variant_to_gene({variant_node.id})')
                if cache_results is None:
                    uncached_variant_annotation_nodes.append(variant_node)

                    # if there is enough in the variant annotation batch process them and empty the array
                    if len(uncached_variant_annotation_nodes) == 1000:
                        self.prepopulate_variant_annotation_cache(uncached_variant_annotation_nodes)
                        uncached_variant_annotation_nodes = []

            # if there are remainder variant node entries left to process
            if uncached_variant_annotation_nodes:
                self.prepopulate_variant_annotation_cache(uncached_variant_annotation_nodes)

        except Exception as e:
            logger.error(f'Exception caught. Exception: {e}')
            ret_val = e
        # return to the caller
        return ret_val

    #######
    # process_variant_annotation_cache - processes an array of un-cached variant nodes.
    #######
    def prepopulate_variant_annotation_cache(self, batch_of_nodes: list) -> bool:
        # init the return value, presume failure
        ret_val = False

        # convert to format for genetics service
        variant_dict = {}
        for node in batch_of_nodes:
            variant_dict[node.id] = node.synonyms
        batch_annotations = self.genetics_services.batch_sequence_variant_to_gene(MYVARIANT, variant_dict)

        # do we have anything to process
        if len(batch_annotations) > 0:
            # open a connection to the redis cache DB
            with self.cache.get_pipeline() as redis_pipe:
                # for each variant
                for seq_var_curie, annotations in batch_annotations.items():
                    # assemble the redis key
                    key = f'{MYVARIANT}.sequence_variant_to_gene({seq_var_curie})'

                    # add the key and data to the list to execute
                    self.cache.set(key, annotations, redis_pipe)

                # write the records out to the cache DB
                redis_pipe.execute()
                ret_val = True

        # return to the caller
        return ret_val

    def process_gwas_associations(self,
                                  gwas_rag: RAG,
                                  gwas_hits: List[GWASHit]):

        missing_variants_count = 0
        p_value_too_high = 0
        predicate = LabeledID(identifier=f'RO:0002609', label=f'related_to')
        gwas_file = GWASFile(file_path=gwas_rag.file_path)
        gwas_node = KNode(gwas_rag.as_node_curie, name=gwas_rag.as_node_label, type=gwas_rag.as_node_type)
        self.normalizer.normalize(gwas_node)

        if not gwas_rag.written:
            self.writer.write_node(gwas_node)

        associations = []

        with GWASFileReader(gwas_file, use_tabix=gwas_file.has_tabix) as gwas_file_reader:
            for gwas_hit in gwas_hits:
                association = gwas_file_reader.get_gwas_association_from_file(gwas_hit)
                if association:
                    if (gwas_rag.max_p_value is None) or (association.p_value <= gwas_rag.max_p_value):
                        self.write_new_association(gwas_node.id,
                                                   gwas_hit.curie,
                                                   predicate,
                                                   association.p_value,
                                                   strength=association.beta,
                                                   namespace=gwas_rag.rag_name,
                                                   project_id=self.project_id,
                                                   project_name=self.project_name)
                        associations.append(association)
                    elif gwas_rag.max_p_value:
                        p_value_too_high += 1
                else:
                    missing_variants_count += 1

        if missing_variants_count > 0:
            logger.warning(f'{gwas_rag.rag_name} had {missing_variants_count} missing variants!')
        if p_value_too_high > 0:
            logger.warning(f'{gwas_rag.rag_name} had {p_value_too_high} variants with p values that exceeded {gwas_rag.max_p_value}!')
        if associations:
            logger.info(f'{gwas_rag.rag_name} had {len(associations)} that should be written')
        else:
            logger.info(f'{gwas_rag.rag_name} failed to find any new valid associations.')

        self.writer.flush()

        return True

    def process_mwas_metabolites(self, mwas_hits: List[MWASHit]):
        processed_mwas_metabolites = []
        for mwas_hit in mwas_hits:
            if not mwas_hit.curie:
                metabolite_node = KNode(mwas_hit.original_curie, name=mwas_hit.original_label, type=node_types.CHEMICAL_SUBSTANCE)
                self.normalizer.normalize(metabolite_node)
                self.writer.write_node(metabolite_node)

                mwas_hit.curie = metabolite_node.id

                processed_mwas_metabolites.append(mwas_hit)

        self.writer.flush()

        return processed_mwas_metabolites

    def process_mwas_associations(self,
                                  mwas_rag: RAG,
                                  mwas_hits: List[MWASHit]):

        missing_metabolites_count = 0
        p_value_too_high = 0
        predicate = LabeledID(identifier=f'RO:0002609', label=f'related_to')
        mwas_file = MWASFile(file_path=mwas_rag.file_path)
        mwas_node = KNode(mwas_rag.as_node_curie, name=mwas_rag.as_node_label, type=mwas_rag.as_node_type)
        self.normalizer.normalize(mwas_node)

        if not mwas_rag.written:
            self.writer.write_node(mwas_node)

        associations = []
        with MWASFileReader(mwas_file) as mwas_file_reader:
            for mwas_hit in mwas_hits:
                if not (mwas_rag.written and mwas_hit.written):
                    association = mwas_file_reader.get_mwas_association_from_file(mwas_hit)
                    if association:
                        if (mwas_rag.max_p_value is None) or (association.p_value <= mwas_rag.max_p_value):
                            self.write_new_association(mwas_node.id,
                                                       mwas_hit.curie,
                                                       predicate,
                                                       association.p_value,
                                                       strength=association.beta,
                                                       namespace=mwas_rag.rag_name,
                                                       project_id=self.project_id,
                                                       project_name=self.project_name)
                            associations.append(association)
                        elif mwas_rag.max_p_value:
                            p_value_too_high += 1
                    else:
                        missing_metabolites_count += 1

        if missing_metabolites_count > 0:
            logger.warning(f'{mwas_rag.rag_name} had {missing_metabolites_count} missing metabolites!')
        if p_value_too_high > 0:
            logger.warning(f'{mwas_rag.rag_name} had {p_value_too_high} metabolites with p values that exceeded {mwas_rag.max_p_value}!')
        if associations:
            logger.info(f'{mwas_rag.rag_name} had {len(associations)} that should be written')
        else:
            logger.info(f'{mwas_rag.rag_name} failed to find any new valid associations.')

        self.writer.flush()

        return True

    def write_new_association(self,
                              source_node_id,
                              associated_node_id,
                              predicate,
                              p_value,
                              strength=None,
                              namespace=None,
                              project_id=None,
                              project_name=None):
        # TODO standardize the predicate with the a service
        #if self.concept_model:
        #    standard_predicate = self.concept_model.standardize_relationship(predicate)
        #else:
        #    logger.warning('GWAS builder: concept_model was missing, predicate standardization failed')
        #    standard_predicate = predicate
        standard_predicate = predicate

        provided_by = 'RAGS_Builder'
        props = {'p_value': p_value}
        if strength:
            props['strength'] = strength

        ctime = time.time()
        new_edge = KEdge(source_id=source_node_id,
                         target_id=associated_node_id,
                         provided_by=provided_by,
                         ctime=ctime,
                         original_predicate=predicate,
                         standard_predicate=standard_predicate,
                         input_id=source_node_id,
                         namespace=namespace,
                         project_id=project_id,
                         project_name=project_name,
                         properties=props)
        
        self.writer.write_edge(new_edge)

        return new_edge
