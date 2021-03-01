from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float
from sqlalchemy.orm import relationship

from app_database import Base

RAGS_PROJECTS_TABLE_NAME = "r_projects"
RAGS_STUDY_TABLE_NAME = "r_studies"
RAGS_ERRORS_TABLE_NAME = "r_errors"
GWAS_HITS_TABLE_NAME = "gwas_hits"
MWAS_HITS_TABLE_NAME = "mwas_hits"


class RAGsProject(Base):
    __tablename__ = RAGS_PROJECTS_TABLE_NAME
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, unique=True)
    studies = relationship("RAGsStudy")


class RAGsStudy(Base):
    __tablename__ = RAGS_STUDY_TABLE_NAME
    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String)
    study_name = Column(String, index=True)
    study_type = Column(String)
    original_trait_id = Column(String)
    original_trait_type = Column(String)
    original_trait_label = Column(String)
    p_value_cutoff = Column(Float)
    max_p_value = Column(Float)
    has_tabix = Column(Boolean)

    searched = Column(Boolean, default=False)
    written = Column(Boolean, default=False)

    num_hits = Column(Integer, nullable=True)

    # number of associations with hits anywhere in the project
    # (that are below the max p value and in this RAG file)
    num_associations = Column(Integer, nullable=True)

    trait_normalized = Column(Boolean, default=False)
    normalized_trait_id = Column(String, nullable=True)
    normalized_trait_label = Column(String, nullable=True)

    project_id = Column(Integer, ForeignKey(f'{RAGS_PROJECTS_TABLE_NAME}.id'))
    gwas_hits = relationship("GWASHit")
    mwas_hits = relationship("MWASHit")
    errors = relationship("RAGsError")


class RAGsError(Base):
    __tablename__ = RAGS_ERRORS_TABLE_NAME

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(Integer, ForeignKey(f'{RAGS_STUDY_TABLE_NAME}.id'))
    error_type = Column(Integer)
    error_message = Column(String)


class GWASHit(Base):
    __tablename__ = GWAS_HITS_TABLE_NAME
    id = Column(Integer, primary_key=True, index=True)
    original_id = Column(String)
    original_name = Column(String)
    normalized = Column(Boolean, default=False)
    normalized_id = Column(String)
    normalized_name = Column(String)

    hgvs = Column(String)
    chrom = Column(String)
    pos = Column(Integer)
    ref = Column(String)
    alt = Column(String)

    # the study_id does imply the project id, but store for faster queries
    project_id = Column(Integer, ForeignKey(f'{RAGS_PROJECTS_TABLE_NAME}.id'))
    study_id = Column(Integer, ForeignKey(f'{RAGS_STUDY_TABLE_NAME}.id'))
    written = Column(Boolean, default=False)


class MWASHit(Base):
    __tablename__ = MWAS_HITS_TABLE_NAME
    id = Column(Integer, primary_key=True, index=True)
    original_id = Column(String)
    original_name = Column(String)
    normalized = Column(Boolean, default=False)
    normalized_id = Column(String)
    normalized_name = Column(String)

    # the study_id does imply the project id, but store for faster queries
    project_id = Column(Integer, ForeignKey(f'{RAGS_PROJECTS_TABLE_NAME}.id'))
    study_id = Column(Integer, ForeignKey(f'{RAGS_STUDY_TABLE_NAME}.id'))
    written = Column(Boolean, default=False)
