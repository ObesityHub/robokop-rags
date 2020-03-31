from rags_src.rags_file_tools import GWASFileReader, MWASFileReader
from rags_src.rags_core import RAG, SignificantHitsContainer, SequenceVariantContainer

from rags_src.graph_components import KNode, KEdge, LabeledID
from rags_src.rags_graph_writer import BufferedWriter
from rags_src.rags_graph_db import RagsGraphDB
from rags_src.rags_file_tools import GWASFile, MWASFile
from rags_src.util import LoggingUtil
from rags_src.services.clingen import ClinGenService
from rags_src.rags_cache import Cache
from rags_src.services.synonymizer import Synonymizer

import rags_src.node_types as node_types
import rags_src.rags_core as rags_core
from rags_src.rags_core import GWASHit, MWASHit

from typing import List
import logging
import os
import time

logger = LoggingUtil.init_logging("rags.rags_graph_builder", logging.INFO, format='medium', logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')


class RagsGraphBuilder(object):

    def __init__(self, graph_db: RagsGraphDB, synonymizer: Synonymizer, cache: Cache):
        self.cache = cache
        self.synonymizer = synonymizer
        self.clingen = ClinGenService()
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

    def prepopulate_variant_synonymization_cache(self, variant_hits: List[GWASHit]):
        # walk through and batch synonymize any variants that need it
        uncached_variants = []
        for variant in variant_hits:
            # any variant without a curie has not been normalized yet
            if not variant.curie:
                if self.cache.get(f'synonymize(HGVS:{variant.hgvs})') is None:
                    uncached_variants.append(variant.hgvs)

                if len(uncached_variants) == 10000:
                    self.process_variant_synonymization_cache(uncached_variants)
                    uncached_variants = []
                
        if uncached_variants:
            self.process_variant_synonymization_cache(uncached_variants)

    def process_variant_synonymization_cache(self, batch_of_hgvs: list):
        batch_synonyms = self.clingen.get_batch_of_synonyms(batch_of_hgvs)
        with self.cache.get_pipeline() as pipe:
            count = 0
            for hgvs_curie, synonyms in batch_synonyms.items():
                key = f'synonymize({hgvs_curie})'
                self.cache.set(key, synonyms, pipe)
                count += 1

                caid_syn = None
                for syn in synonyms:
                    if syn.identifier.startswith('CAID'):
                        caid_syn = syn
                        break

                if caid_syn:
                    synonyms.remove(caid_syn)
                    self.cache.set(f'synonymize({caid_syn.identifier})', synonyms, pipe)
                    count += 1

                if count == 1000:
                    pipe.execute()
                    count = 0

            if count > 0:
                pipe.execute()

    def process_gwas_variants(self, gwas_hits: List[GWASHit]):
        processed_gwas_variants = []
        for gwas_hit in gwas_hits:
            if not gwas_hit.curie:
                curie_hgvs = f'HGVS:{gwas_hit.hgvs}'
                variant_node = KNode(curie_hgvs, name=gwas_hit.hgvs, type=node_types.SEQUENCE_VARIANT)
                self.synonymizer.synonymize(variant_node)

                rsids = variant_node.get_labeled_ids_by_prefix('DBSNP')
                if rsids:
                    variant_node.name = next(iter(rsids)).label
                else:
                    caids = variant_node.get_labeled_ids_by_prefix('CAID')
                    if caids:
                        variant_node.name = next(iter(caids)).label

                self.writer.write_node(variant_node)

                gwas_hit.curie = variant_node.id

                processed_gwas_variants.append(gwas_hit)

        self.writer.flush()

        return processed_gwas_variants

    def process_gwas_associations(self,
                                  project_id: str,
                                  project_name: str,
                                  gwas_rag: RAG,
                                  gwas_hits: List[GWASHit]):

        missing_variants_count = 0
        p_value_too_high = 0
        predicate = LabeledID(identifier=f'RO:0002609', label=f'related_to')
        gwas_file = GWASFile(file_path=gwas_rag.file_path)
        gwas_node = KNode(gwas_rag.as_node_curie, name=gwas_rag.as_node_label, type=gwas_rag.as_node_type)
        self.synonymizer.synonymize(gwas_node)

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
                                                   project_id=project_id,
                                                   project_name=project_name)
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
                self.synonymizer.synonymize(metabolite_node)
                self.writer.write_node(metabolite_node)

                mwas_hit.curie = metabolite_node.id

                processed_mwas_metabolites.append(mwas_hit)

        self.writer.flush()

        return processed_mwas_metabolites

    def process_mwas_associations(self,
                                  project_id: str,
                                  project_name: str,
                                  mwas_rag: RAG,
                                  mwas_hits: List[MWASHit]):

        missing_metabolites_count = 0
        p_value_too_high = 0
        predicate = LabeledID(identifier=f'RO:0002609', label=f'related_to')
        mwas_file = MWASFile(file_path=mwas_rag.file_path)
        mwas_node = KNode(mwas_rag.as_node_curie, name=mwas_rag.as_node_label, type=mwas_rag.as_node_type)
        self.synonymizer.synonymize(mwas_node)

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
                                                       project_id=project_id,
                                                       project_name=project_name)
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
