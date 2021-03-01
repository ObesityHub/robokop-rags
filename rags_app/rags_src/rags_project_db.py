from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import rags_src.rags_core as rags_core
from rags_src.rags_core import SignificantHitsContainer, GWASHit, MWASHit
from rags_src.util import LoggingUtil

import rags_src.rags_project_db_models as rags_db_models

import logging
import os

from typing import List

logger = LoggingUtil.init_logging("rags.rags_project_db", logging.INFO, format='medium', logFilePath=f'{os.environ["RAGS_HOME"]}/logs/')


class RagsProjectDB(object):
    """
    This is a wrapper to encapsulate database calls

    A SQLAlchemy Session should be initialized and closed outside of this class

    IDEs might warn against "== False" syntax in the db queries but it is correct for sqlalchemy

    """
    def __init__(self, db_session: Session):
        self.db = db_session

    def create_project(self, project_name: str):
        try:
            project = rags_db_models.RAGsProject(name=project_name)
            self.db.add(project)
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f'Error adding project ({project_name}): {e}')
            return False
        return True

    def delete_project(self, project_id: int):
        project = self.get_project_by_id(project_id)
        for study in project.studies:
            self.delete_study(study, delay_commit=True)
        self.db.delete(project)
        self.db.commit()
        return True

    def get_projects(self):
        return self.db.query(rags_db_models.RAGsProject).all()

    def get_project_by_id(self, project_id: int):
        return self.db.query(rags_db_models.RAGsProject).filter(rags_db_models.RAGsProject.id == project_id).first()

    def get_project_by_name(self, project_name: str):
        return self.db.query(rags_db_models.RAGsProject).filter(rags_db_models.RAGsProject.name == project_name).first()

    def project_exists_by_id(self, project_id: int):
        if self.db.query(rags_db_models.RAGsProject).filter(rags_db_models.RAGsProject.id == project_id).first():
            return True
        else:
            return False

    def project_exists_by_name(self, project_name: str):
        if self.db.query(rags_db_models.RAGsProject).filter(rags_db_models.RAGsProject.name == project_name).first():
            return True
        else:
            return False

    def create_study(self,
                     project_id: int,
                     file_path: str,
                     study_name: str,
                     study_type: str,
                     original_trait_id: str,
                     original_trait_type: str,
                     original_trait_label: str,
                     p_value_cutoff: float,
                     max_p_value: float,
                     has_tabix: bool = False):

        new_study = rags_db_models.RAGsStudy(project_id=project_id,
                                             file_path=file_path,
                                             study_name=study_name,
                                             study_type=study_type,
                                             original_trait_id=original_trait_id,
                                             original_trait_type=original_trait_type,
                                             original_trait_label=original_trait_label,
                                             p_value_cutoff=p_value_cutoff,
                                             max_p_value=max_p_value,
                                             has_tabix=has_tabix)
        self.db.add(new_study)
        self.db.commit()
        return True

    def get_all_studies(self, project_id: int) -> List[rags_db_models.RAGsStudy]:
        return self.db.query(rags_db_models.RAGsStudy).filter(rags_db_models.RAGsStudy.project_id == project_id).all()

    def get_study_by_id(self, study_id: int) -> rags_db_models.RAGsStudy:
        return self.db.query(rags_db_models.RAGsStudy).filter(rags_db_models.RAGsStudy.id == study_id).first()

    def get_study_by_name(self, study_name: str) -> rags_db_models.RAGsStudy:
        return self.db.query(rags_db_models.RAGsStudy).filter(rags_db_models.RAGsStudy.study_name == study_name).first()

    def study_exists(self, project_id: int, study_name: str) -> rags_db_models.RAGsStudy:
        return self.db.query(rags_db_models.RAGsStudy).filter(rags_db_models.RAGsStudy.study_name == study_name).filter(
            rags_db_models.RAGsStudy.project_id == project_id).first()

    def delete_study(self, study: rags_db_models.RAGsStudy, delay_commit: bool = False) -> bool:
        db_study = self.get_study_by_id(study.id)
        if not db_study:
            return False
        for hit in db_study.gwas_hits:
            self.db.delete(hit)
        for hit in db_study.mwas_hits:
            self.db.delete(hit)
        for error in db_study.errors:
            self.db.delete(error)
        self.db.delete(db_study)
        if not delay_commit:
            self.db.commit()
        return True

    def clear_study_errors(self, study_id: int, delay_commit: bool = False):
        r_errors = self.get_study_by_id(study_id).errors
        for r in r_errors:
            self.db.delete(r)
        if not delay_commit:
            self.db.commit()

    def clear_study_errors_by_type(self, study_id: int, error_type: int, delay_commit: bool = False):
        r_errors = self.get_study_by_id(study_id).errors
        for r in r_errors:
            if r.error_type == error_type:
                self.db.delete(r)
        if not delay_commit:
            self.db.commit()

    def create_study_error(self, study_id: int, error_type: int, error_message: str, delay_commit: bool = False):
        new_study_error = rags_db_models.RAGsError(study_id=study_id,
                                                   error_type=error_type,
                                                   error_message=error_message)
        self.db.add(new_study_error)
        if not delay_commit:
            self.db.commit()

    def get_all_gwas_hits(self, project_id: int) -> List[rags_db_models.GWASHit]:
        return self.db.query(rags_db_models.GWASHit).\
            filter(rags_db_models.GWASHit.project_id == project_id).all()

    def get_unprocessed_gwas_hits(self, project_id: int) -> List[rags_db_models.GWASHit]:
        return self.db.query(rags_db_models.GWASHit).\
            filter(rags_db_models.GWASHit.project_id == project_id).\
            filter(rags_db_models.GWASHit.normalized == False).all()

    def get_unwritten_gwas_hits(self, project_id: int) -> List[rags_db_models.GWASHit]:
        return self.db.query(rags_db_models.GWASHit).\
            filter(rags_db_models.GWASHit.project_id == project_id).\
            filter(rags_db_models.GWASHit.written == False).all()

    def get_all_mwas_hits(self, project_id: int) -> List[rags_db_models.MWASHit]:
        return self.db.query(rags_db_models.MWASHit).\
            filter(rags_db_models.MWASHit.project_id == project_id).all()

    def get_unprocessed_mwas_hits(self, project_id: int) -> List[rags_db_models.MWASHit]:
        return self.db.query(rags_db_models.MWASHit).\
            filter(rags_db_models.MWASHit.project_id == project_id).\
            filter(rags_db_models.MWASHit.normalized == False).all()

    def get_unwritten_mwas_hits(self, project_id: int) -> List[rags_db_models.MWASHit]:
        return self.db.query(rags_db_models.MWASHit).\
            filter(rags_db_models.MWASHit.project_id == project_id).\
            filter(rags_db_models.MWASHit.written == False).all()

    def save_hits(self,
                  project_id: int,
                  study: rags_db_models.RAGsStudy,
                  hits_container: SignificantHitsContainer,
                  delay_commit: bool = False):
        if study.study_type == rags_core.GWAS:
            for hit in hits_container.iterate():
                self.create_gwas_hit(project_id, study.id, hit, delay_commit=True)
        elif study.study_type == rags_core.MWAS:
            for hit in hits_container.iterate():
                self.create_mwas_hit(project_id, study.id, hit, delay_commit=True)
        if not delay_commit:
            self.db.commit()

    def create_gwas_hit(self,
                        project_id: int,
                        study_id: int,
                        hit: GWASHit,
                        delay_commit: bool = False):
        new_gwas_hit = rags_db_models.GWASHit(project_id=project_id,
                                              study_id=study_id,
                                              hgvs=hit.hgvs,
                                              chrom=hit.chrom,
                                              pos=hit.pos,
                                              ref=hit.ref,
                                              alt=hit.alt,
                                              original_id=hit.original_id,
                                              original_name=hit.original_name,
                                              normalized=False)
        self.db.add(new_gwas_hit)
        if not delay_commit:
            self.db.commit()
        return True

    def create_mwas_hit(self, project_id: int, study_id: int, hit: MWASHit, delay_commit: bool = False):
        new_mwas_hit = rags_db_models.MWASHit(project_id=project_id,
                                              study_id=study_id,
                                              original_id=hit.original_id,
                                              original_name=hit.original_name,
                                              normalized=False)
        self.db.add(new_mwas_hit)
        if not delay_commit:
            self.db.commit()
        return True

    def commit_orm_transactions(self):
        self.db.commit()
