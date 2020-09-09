from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import rags_src.rags_core as rags_core
from rags_src.rags_core import RAG, SignificantHitsContainer, GWASHit, MWASHit
from rags_src.util import LoggingUtil

import rags_src.rags_db_models as rags_db_models

import logging
import os

from typing import List

logger = LoggingUtil.init_logging("rags.rags_project_db", logging.INFO, format='medium', logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')


class RagsProjectDB(object):
    """
    This is a wrapper to encapsulate the DB code.

    Here we also convert objects to and from their SQLAlchemy counterparts.
    """
    def __init__(self, db_session: Session):
        self.db = db_session

    def create_project(self, project_name: str):
        try:
            project = rags_db_models.Project(name=project_name)
            self.db.add(project)
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f'Error adding project ({project_name}): {e}')
            return False
        return True

    def delete_project(self, project_id: int):
        project = self.get_project_by_id(project_id)
        for rag in project.rags:
            self.delete_rag(rag, delay_commit=True)
        self.db.delete(project)
        self.db.commit()
        return True

    def get_projects(self):
        return self.db.query(rags_db_models.Project).all()

    def get_project_by_id(self, project_id: int):
        return self.db.query(rags_db_models.Project).filter(rags_db_models.Project.id == project_id).first()

    def get_project_by_name(self, project_name: str):
        return self.db.query(rags_db_models.Project).filter(rags_db_models.Project.name == project_name).first()

    def project_exists_by_id(self, project_id: int):
        if self.db.query(rags_db_models.Project).filter(rags_db_models.Project.id == project_id).first():
            return True
        else:
            return False

    def project_exists_by_name(self, project_name: str):
        if self.db.query(rags_db_models.Project).filter(rags_db_models.Project.name == project_name).first():
            return True
        else:
            return False

    def create_rag(self,
                   project_id: int,
                   rag_name: str,
                   rag_type: str,
                   file_path: str,
                   trait_type: str,
                   trait_curie: str,
                   trait_label: str,
                   p_value_cutoff: float,
                   max_p_value: float,
                   has_tabix: bool = False):

        new_rag = rags_db_models.RAG(rag_name=rag_name,
                                     rag_type=rag_type,
                                     project_id=project_id,
                                     trait_type=trait_type,
                                     trait_curie=trait_curie,
                                     trait_label=trait_label,
                                     p_value_cutoff=p_value_cutoff,
                                     max_p_value=max_p_value,
                                     file_path=file_path,
                                     searched=False,
                                     written=False,
                                     validated=False,
                                     has_tabix=has_tabix)
        self.db.add(new_rag)
        self.db.commit()
        return True

    def get_rags(self, project_id: int) -> List[rags_db_models.RAG]:
        return self.db.query(rags_db_models.RAG).filter(rags_db_models.RAG.project_id == project_id).all()

    def get_rag_by_id(self, rag_id: int) -> rags_db_models.RAG:
        return self.db.query(rags_db_models.RAG).filter(rags_db_models.RAG.id == rag_id).first()

    def get_rag_by_name(self, rag_name: str) -> rags_db_models.RAG:
        return self.db.query(rags_db_models.RAG).filter(rags_db_models.RAG.rag_name == rag_name).first()

    def rag_exists(self, project_id: int, rag_name: str) -> rags_db_models.RAG:
        return self.db.query(rags_db_models.RAG).filter(rags_db_models.RAG.rag_name == rag_name).filter(
            rags_db_models.RAG.project_id == project_id).first()

    def update_rag(self, rag: RAG, delay_commit: bool = False) -> bool:
        db_rag = self.get_rag_by_id(rag.id)
        db_rag.searched = rag.searched
        db_rag.written = rag.written
        db_rag.validated = rag.validated
        if db_rag.searched:
            db_rag.num_hits = rag.num_hits
        else:
            db_rag.num_hits = 0
        if not delay_commit:
            self.db.commit()
        return True

    def delete_rag(self, rag: RAG, delay_commit: bool = False) -> bool:
        db_rag = self.get_rag_by_id(rag.id)
        if not db_rag:
            return False
        for hit in db_rag.gwas_hits:
            self.db.delete(hit)
        for hit in rag.mwas_hits:
            self.db.delete(hit)
        self.db.delete(db_rag)
        if not delay_commit:
            self.db.commit()
        return True

    def get_all_gwas_hits(self, project_id: int) -> List[rags_db_models.GWASHit]:
        return self.db.query(rags_db_models.GWASHit).\
            filter(rags_db_models.GWASHit.project_id == project_id).all()

    def get_unprocessed_gwas_hits(self, project_id: int) -> List[rags_db_models.GWASHit]:
        return self.db.query(rags_db_models.GWASHit).\
            filter(rags_db_models.GWASHit.project_id == project_id).\
            filter(rags_db_models.GWASHit.curie == '').all()

    def get_all_mwas_hits(self, project_id: int) -> List[rags_db_models.MWASHit]:
        return self.db.query(rags_db_models.MWASHit).\
            filter(rags_db_models.MWASHit.project_id == project_id).all()

    def get_unprocessed_mwas_hits(self, project_id: int) -> List[rags_db_models.MWASHit]:
        return self.db.query(rags_db_models.MWASHit).\
            filter(rags_db_models.MWASHit.project_id == project_id).\
            filter(rags_db_models.MWASHit.curie == '').all()

    def save_hits(self, project_id: int, rag: RAG, hits_container: SignificantHitsContainer):
        if rag.rag_type == rags_core.GWAS:
            for hit in hits_container.iterate():
                self.create_gwas_hit(project_id, rag.id, hit, delay_commit=True)
        elif rag.rag_type == rags_core.MWAS:
            for hit in hits_container.iterate():
                self.create_mwas_hit(project_id, rag.id, hit, delay_commit=True)
        self.db.commit()

    def create_gwas_hit(self, project_id: int, rag_id: int, hit: GWASHit, delay_commit: bool = False):
        new_gwas_hit = rags_db_models.GWASHit(project_id=project_id,
                                              rag_id=rag_id,
                                              hgvs=hit.hgvs,
                                              chrom=hit.chrom,
                                              pos=hit.pos,
                                              ref=hit.ref,
                                              alt=hit.alt,
                                              curie=hit.curie)
        self.db.add(new_gwas_hit)
        if not delay_commit:
            self.db.commit()
        return True

    def create_mwas_hit(self, project_id: int, rag_id: int, hit: MWASHit, delay_commit: bool = False):
        new_mwas_hit = rags_db_models.MWASHit(project_id=project_id,
                                              rag_id=rag_id,
                                              original_curie=hit.original_curie,
                                              original_label=hit.original_label,
                                              curie=hit.curie)
        self.db.add(new_mwas_hit)
        if not delay_commit:
            self.db.commit()
        return True

    def commit_orm_transactions(self):
        self.db.commit()









